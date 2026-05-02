"""方案 Agent（LLM 增强版）"""
import logging
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.core.prompts import (
    PLANNING_SYSTEM_PROMPT,
    PLANNING_USER_TEMPLATE,
)
from omniops.models import CognitiveSummary, Session, Suggestion, SuggestionAction

logger = logging.getLogger(__name__)


class PlanningAgent(BaseAgent):
    """方案 Agent：生成结构化修复建议（LLM 增强 + 模板回退）"""

    name = "planning"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """生成修复方案"""
        diagnosis = session.diagnosis_result
        impact = session.impact

        root_cause = diagnosis.root_cause if diagnosis else "未知根因"
        confidence = diagnosis.confidence if diagnosis else 0.0

        # 影响范围文本
        impact_text = ""
        if impact:
            impact_text = f"- 受影响网元：{', '.join(impact.affected_ne)}\n"
            if impact.affected_links:
                impact_text += f"- 受影响链路：{', '.join(impact.affected_links)}\n"
            if impact.affected_services:
                impact_text += f"- 受影响业务：{', '.join(impact.affected_services)}"

        # 尝试 LLM 生成
        suggestion = None
        try:
            from omniops.core.providers import get_provider
            get_provider()
            suggestion = await self._llm_planning(
                root_cause=root_cause,
                confidence=confidence,
                impact_text=impact_text,
            )
        except Exception as e:
            logger.warning(f"LLM planning failed, falling back to template: {e}")

        # 如果 LLM 失败，使用模板
        if not suggestion:
            suggestion = self._match_template(root_cause)

        session.suggestion = suggestion

        evidence_list: List[Dict[str, Any]] = [
            {"type": "action", "source": f"step {a.step}", "value": a.action}
            for a in suggestion.suggested_actions
        ]

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="verification",
            session_id=session.session_id,
            conclusion=f"修复方案已生成：{len(suggestion.suggested_actions)} 个步骤，风险等级 {suggestion.risk_level}",
            confidence=confidence,
            evidence=evidence_list,
            uncertainty=None,
            required_action="验证方案可行性和一致性",
            context_window_used=0,
        )

    async def _llm_planning(
        self,
        root_cause: str,
        confidence: float,
        impact_text: str,
    ) -> Optional[Suggestion]:
        """使用 LLM 生成修复方案"""
        try:
            user_message = PLANNING_USER_TEMPLATE.format(
                root_cause=root_cause,
                confidence=confidence,
                impact=impact_text or "暂无影响评估信息",
            )

            from omniops.core.providers import get_provider
            provider = get_provider()
            result = await provider.generate_json(
                system=PLANNING_SYSTEM_PROMPT,
                user_message=user_message,
            )

            # 解析结果
            actions = [
                SuggestionAction(
                    step=a["step"],
                    action=a["action"],
                    estimated_time=a.get("estimated_time"),
                    service_impact=a.get("service_impact"),
                )
                for a in result.get("suggested_actions", [])
            ]

            return Suggestion(
                root_cause=result.get("root_cause", root_cause),
                suggested_actions=actions,
                required_tools=result.get("required_tools", []),
                fallback_plan=result.get("fallback_plan"),
                risk_level=result.get("risk_level", "medium"),
                needs_approval=result.get("needs_approval", True),
            )

        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            return None

    def _match_template(
        self,
        root_cause: str,
    ) -> Suggestion:
        """匹配方案模板"""
        templates = {
            "数据库": [
                SuggestionAction(step=1, action="检查数据库进程状态和连接数", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="查看数据库错误日志，定位故障原因", estimated_time="15min", service_impact="none"),
                SuggestionAction(step=3, action="如为配置类告警，执行配置恢复或同步", estimated_time="20min", service_impact="requires_planned"),
            ],
            "光链路": [
                SuggestionAction(step=1, action="检查光纤端面清洁度", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="使用 OTDR 测试光纤长度和损耗", estimated_time="15min", service_impact="none"),
                SuggestionAction(step=3, action="若 OTDR 发现异常点，定位并更换光纤段", estimated_time="30min", service_impact="brief_interrupt"),
            ],
            "光功率": [
                SuggestionAction(step=1, action="清洁光纤端面", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="测量收光功率，确认是否低于阈值", estimated_time="5min", service_impact="none"),
                SuggestionAction(step=3, action="若无效，更换光模块", estimated_time="30min", service_impact="brief_interrupt"),
            ],
            "电源": [
                SuggestionAction(step=1, action="检查电源模块指示灯状态", estimated_time="5min", service_impact="none"),
                SuggestionAction(step=2, action="测量输入电压，确认是否在正常范围", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=3, action="若电压异常，检查外部供电和 UPS", estimated_time="20min", service_impact="none"),
                SuggestionAction(step=4, action="若电源模块故障，联系供应商更换", estimated_time="60min", service_impact="requires_planned"),
            ],
            "板卡": [
                SuggestionAction(step=1, action="检查板卡指示灯和日志", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="尝试重启板卡（先确认是否有备板）", estimated_time="15min", service_impact="requires_planned"),
                SuggestionAction(step=3, action="若无备板，联系备件支持", estimated_time="30min", service_impact="none"),
            ],
        }

        for keyword, actions in templates.items():
            if keyword in root_cause:
                risk = "high" if keyword == "电源" else "medium"
                return Suggestion(
                    root_cause=root_cause,
                    suggested_actions=actions,
                    required_tools=self._get_tools_for_keyword(keyword),
                    fallback_plan="若上述步骤无效，升级至现场支持团队",
                    risk_level=risk,
                    needs_approval=risk in ("high", "medium"),
                )

        # 默认模板
        return Suggestion(
            root_cause=root_cause,
            suggested_actions=[
                SuggestionAction(step=1, action="收集告警详细信息", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="联系技术支持获取进一步指导", estimated_time="30min", service_impact="none"),
            ],
            required_tools=["告警日志导出工具"],
            fallback_plan="若上述步骤无效，升级至现场支持团队",
            risk_level="low",
            needs_approval=False,
        )

    def _get_tools_for_keyword(self, keyword: str) -> List[str]:
        """根据根因关键词获取所需工具"""
        tools_map = {
            "数据库": ["数据库客户端", "日志分析工具", "备份恢复工具"],
            "光链路": ["OTDR", "光纤清洁棒", "备用光纤"],
            "光功率": ["光功率计", "备用光模块", "光纤清洁棒"],
            "电源": ["万用表", "备用电源模块", "UPS 状态查询"],
            "板卡": ["备板", "板卡日志导出工具"],
        }
        return tools_map.get(keyword, ["通用工具"])
