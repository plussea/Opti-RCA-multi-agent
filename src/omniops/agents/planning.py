"""方案 Agent"""
from typing import Any, Dict, List, Optional, Tuple

from omniops.agents.base import BaseAgent
from omniops.models import CognitiveSummary, Session, Suggestion, SuggestionAction


class PlanningAgent(BaseAgent):
    """方案 Agent：生成结构化修复建议"""

    name = "planning"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """生成修复方案"""
        diagnosis = session.diagnosis_result

        root_cause = diagnosis.root_cause if diagnosis else "未知根因"
        confidence = diagnosis.confidence if diagnosis else 0.0

        # 基于根因匹配方案模板
        actions, risk_level, tools = self._match_template(root_cause)

        suggestion = Suggestion(
            root_cause=root_cause,
            suggested_actions=actions,
            required_tools=tools,
            fallback_plan="若上述步骤无效，升级至现场支持团队",
            risk_level=risk_level,
            needs_approval=risk_level in ("high", "medium"),
        )

        session.suggestion = suggestion

        evidence_list: List[Dict[str, Any]] = [
            {"type": "action", "source": f"step {a.step}", "value": a.action}
            for a in actions
        ]

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="verification",
            session_id=session.session_id,
            conclusion=f"修复方案已生成：{len(actions)} 个步骤，风险等级 {risk_level}",
            confidence=confidence,
            evidence=evidence_list,
            uncertainty=None,
            required_action="验证方案可行性和一致性",
            context_window_used=0,
        )

    def _match_template(
        self,
        root_cause: str,
    ) -> Tuple[List[SuggestionAction], str, List[str]]:
        """匹配方案模板"""
        templates = {
            "光链路": (
                [
                    SuggestionAction(step=1, action="检查光纤端面清洁度", estimated_time="10min", service_impact="none"),
                    SuggestionAction(step=2, action="使用 OTDR 测试光纤长度和损耗", estimated_time="15min", service_impact="none"),
                    SuggestionAction(step=3, action="若 OTDR 发现异常点，定位并更换光纤段", estimated_time="30min", service_impact="brief_interrupt"),
                ],
                "medium",
                ["OTDR", "光纤清洁棒", "备用光纤"],
            ),
            "光功率": (
                [
                    SuggestionAction(step=1, action="清洁光纤端面", estimated_time="10min", service_impact="none"),
                    SuggestionAction(step=2, action="测量收光功率，确认是否低于阈值", estimated_time="5min", service_impact="none"),
                    SuggestionAction(step=3, action="若无效，更换光模块", estimated_time="30min", service_impact="brief_interrupt"),
                ],
                "medium",
                ["光功率计", "备用光模块", "光纤清洁棒"],
            ),
            "电源": (
                [
                    SuggestionAction(step=1, action="检查电源模块指示灯状态", estimated_time="5min", service_impact="none"),
                    SuggestionAction(step=2, action="测量输入电压，确认是否在正常范围", estimated_time="10min", service_impact="none"),
                    SuggestionAction(step=3, action="若电压异常，检查外部供电和 UPS", estimated_time="20min", service_impact="none"),
                    SuggestionAction(step=4, action="若电源模块故障，联系供应商更换", estimated_time="60min", service_impact="requires_planned"),
                ],
                "high",
                ["万用表", "备用电源模块", "UPS 状态查询"],
            ),
            "板卡": (
                [
                    SuggestionAction(step=1, action="检查板卡指示灯和日志", estimated_time="10min", service_impact="none"),
                    SuggestionAction(step=2, action="尝试重启板卡（先确认是否有备板）", estimated_time="15min", service_impact="requires_planned"),
                    SuggestionAction(step=3, action="若无备板，联系备件支持", estimated_time="30min", service_impact="none"),
                ],
                "medium",
                ["备板", "板卡日志导出工具"],
            ),
        }

        for keyword, (actions, risk, tools) in templates.items():
            if keyword in root_cause:
                return actions, risk, tools

        # 默认模板
        return (
            [
                SuggestionAction(step=1, action="收集告警详细信息", estimated_time="10min", service_impact="none"),
                SuggestionAction(step=2, action="联系技术支持获取进一步指导", estimated_time="30min", service_impact="none"),
            ],
            "low",
            ["告警日志导出工具"],
        )