"""诊断 Agent"""
from typing import Any, Dict, List, Optional, Tuple

from omniops.agents.base import BaseAgent
from omniops.models import CognitiveSummary, DiagnosisResult, Evidence, Session


DIAGNOSIS_PROMPT_TEMPLATE = """你是一名资深光网络运维专家，擅长通过告警关联分析定位根因。

已收到以下标准化告警表：
{alarms}

历史相似案例（参考）：
{similar_cases}

请按以下步骤分析：
1. 识别告警模式（单点故障/多点级联/性能劣化）
2. 关联告警码与常见根因
3. 给出最可能的根因（简洁描述）
4. 评估置信度（0-1）
5. 列出关键证据

请以 JSON 格式输出诊断结果，包含：root_cause, confidence (0-1), evidence 列表
"""


class DiagnosisAgent(BaseAgent):
    """诊断 Agent：基于规则 + LLM 推理进行根因分析"""

    name = "diagnosis"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """分析告警表，输出根因假设"""
        records = session.structured_data
        similar_cases = context.get("similar_cases", []) if context else []

        # 告警码聚合分析
        alarm_codes: Dict[str, int] = {}
        for r in records:
            code = r.alarm_code or r.alarm_name or "unknown"
            alarm_codes[code] = alarm_codes.get(code, 0) + 1

        # 规则推理：基于已知告警码模式
        root_cause, confidence, evidence = self._rule_based_diagnosis(records, alarm_codes)

        # 如果有相似案例，提升置信度
        if similar_cases:
            avg_similarity = sum(getattr(c, "similarity", 0) for c in similar_cases) / max(len(similar_cases), 1)
            confidence = min(confidence + avg_similarity * 0.1, 0.99)

        # 构建证据
        evidence_list: List[Evidence] = []
        for code, count in alarm_codes.items():
            for r in records:
                if (r.alarm_code == code or r.alarm_name == code) and len(evidence_list) < 10:
                    evidence_list.append(
                        Evidence(
                            type="alarm",
                            source=r.ne_name,
                            code=code,
                            time=r.occur_time.isoformat() if r.occur_time else None,
                        )
                    )
                    break

        diagnosis = DiagnosisResult(
            root_cause=root_cause,
            confidence=confidence,
            evidence=evidence_list,
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
            evidence=[e.model_dump() for e in evidence_list],
            uncertainty=diagnosis.uncertainty,
            required_action="根据根因评估影响范围",
            context_window_used=len(records),
        )

    def _rule_based_diagnosis(
        self,
        records: List[Any],
        alarm_codes: Dict[str, int],
    ) -> Tuple[str, float, List[Evidence]]:
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
        top_alarm = max(alarm_codes, key=alarm_codes.get, default="unknown")
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