"""诊断 Agent（LLM 增强版）"""
import logging
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.core.llm_client import (
    DIAGNOSIS_SYSTEM_PROMPT,
    DIAGNOSIS_USER_TEMPLATE,
    get_alarm_dict_text,
    get_llm_client as _get_llm_client,
)
from omniops.models import CognitiveSummary, DiagnosisResult, Evidence, Session
from omniops.rag import search_similar_cases

logger = logging.getLogger(__name__)


class DiagnosisAgent(BaseAgent):
    """诊断 Agent：基于 LLM + 规则 + RAG 进行根因分析"""

    name = "diagnosis"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """分析告警表，输出根因假设（优先规则，辅以 LLM）"""
        records = session.structured_data

        # 规则推理：基于已知告警码模式
        alarm_codes = []
        for r in records:
            if r.alarm_code:
                alarm_codes.append(r.alarm_code)

        # 搜索相似案例
        similar_cases = []
        if alarm_codes:
            try:
                case_results = await search_similar_cases(
                    query=" ".join(alarm_codes),
                    alarm_codes=list(set(alarm_codes)),
                    top_k=3,
                )
                similar_cases = case_results
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        # 尝试规则匹配
        root_cause, confidence, evidence = self._rule_based_diagnosis(records, alarm_codes)

        # 如果配置了 LLM provider，尝试 LLM 增强
        try:
            from omniops.core.providers import get_provider
            provider = get_provider()
            try:
                llm_result = await self._llm_diagnosis(
                    records=records,
                    similar_cases=similar_cases,
                )
                # 融合 LLM 结果和规则结果
                if llm_result and llm_result.get("confidence", 0) > confidence:
                    root_cause = llm_result["root_cause"]
                    confidence = llm_result["confidence"]
                    if llm_result.get("evidence"):
                        evidence = [Evidence(**e) for e in llm_result["evidence"]]
            except Exception as e:
                logger.warning(f"LLM diagnosis failed, falling back to rules: {e}")
        except Exception:
            pass  # No LLM provider configured, skip

        # 构建诊断结果
        diagnosis = DiagnosisResult(
            root_cause=root_cause,
            confidence=confidence,
            evidence=evidence,
            uncertainty=self._assess_uncertainty(records),
            agent_chain=[self.name],
        )

        session.diagnosis_result = diagnosis

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="impact",
            session_id=session.session_id,
            conclusion=root_cause,
            confidence=confidence,
            evidence=[e.model_dump() for e in evidence],
            uncertainty=diagnosis.uncertainty,
            required_action="根据根因评估影响范围",
            context_window_used=len(records),
        )

    async def _llm_diagnosis(
        self,
        records: List[Any],
        similar_cases: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 进行诊断"""
        try:
            # 构建告警表文本
            alarms_text = "\n".join([
                f"- {r.ne_name}: {r.alarm_code or r.alarm_name or 'unknown'} "
                f"({r.severity.value if r.severity else 'unknown'}) "
                f"at {r.occur_time or 'unknown'}"
                for r in records
            ])

            # 构建相似案例文本
            cases_text = "\n".join([
                f"- [{c['metadata'].get('root_cause', 'unknown')}] "
                f"(相似度: {c['similarity']:.2f})"
                for c in similar_cases[:3]
            ]) if similar_cases else "无相似案例"

            user_message = DIAGNOSIS_USER_TEMPLATE.format(
                alarms=alarms_text,
                similar_cases=cases_text,
                alarm_dict=get_alarm_dict_text(),
            )

            from omniops.core.providers import get_provider
            provider = get_provider()
            result = await provider.generate_json(
                system=DIAGNOSIS_SYSTEM_PROMPT,
                user_message=user_message,
            )

            return result

        except Exception as e:
            logger.error(f"LLM diagnosis failed: {e}")
            return None

    def _rule_based_diagnosis(
        self,
        records: List[Any],
        alarm_codes: List[str],
    ) -> tuple:
        """基于规则的简单诊断逻辑"""
        # 已知告警模式映射
        patterns = {
            ("LINK_FAIL",): ("光链路故障", 0.85),
            ("POWER_LOW",): ("电源故障或供电不足", 0.80),
            ("BER_HIGH",): ("光功率劣化导致误码", 0.82),
            ("OTU_LOF",): ("光通道帧丢失，可能光纤劣化", 0.88),
            ("LOS",): ("光信号丢失", 0.90),
            ("BD_STATUS",): ("板卡状态异常", 0.75),
        }

        # 匹配模式
        for codes, (cause, conf) in patterns.items():
            if all(c in alarm_codes for c in codes):
                evidence = [
                    Evidence(type="alarm", source=r.ne_name, code=c)
                    for c in codes
                    for r in records
                    if r.alarm_code == c
                ]
                return cause, conf, evidence

        # 默认诊断
        top_alarm = max(
            set(alarm_codes), key=lambda x: alarm_codes.count(x), default="unknown"
        )
        return (
            f"初步判定：{top_alarm} 告警为主，需进一步分析",
            0.60,
            [
                Evidence(type="alarm", source=r.ne_name, code=top_alarm)
                for r in records[:3]
            ],
        )

    def _assess_uncertainty(self, records: List[Any]) -> Optional[str]:
        """评估诊断不确定性"""
        if not records:
            return "无告警数据，无法诊断"

        has_unknown_code = any(not r.alarm_code for r in records)

        if has_unknown_code:
            return "部分告警缺少告警码，影响诊断准确率，建议补充完整信息"

        return None