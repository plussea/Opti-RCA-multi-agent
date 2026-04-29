"""感知 Agent"""
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.models import CognitiveSummary, Session


class PerceptionAgent(BaseAgent):
    """感知 Agent：负责解析输入、提取结构化数据"""

    name = "perception"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """将原始告警数据转换为标准化告警表"""
        records = session.structured_data

        # 感知层汇总
        ne_names = set()
        for r in records:
            if r.ne_name:
                ne_names.add(r.ne_name)
        ne_count = len(ne_names)
        alarm_count = len(records)
        severity_counts: Dict[str, int] = {}
        for r in records:
            if r.severity:
                sev = r.severity.value
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # 生成认知摘要
        evidence_list: List[Dict[str, Any]] = [
            {
                "type": "alarm",
                "source": r.ne_name,
                "code": r.alarm_code or r.alarm_name or "unknown",
                "value": r.severity.value if r.severity else "unknown",
                "time": r.occur_time.isoformat() if r.occur_time else None,
            }
            for r in records[:10]  # 只保留前 10 条证据
        ]

        summary = CognitiveSummary(
            from_agent=self.name,
            to_agent="router",
            session_id=session.session_id,
            conclusion=f"感知完成：提取 {alarm_count} 条告警，来自 {ne_count} 个网元",
            confidence=1.0,
            evidence=evidence_list,
            uncertainty=None,
            required_action=f"根据 {alarm_count} 条告警进行路由决策",
            context_window_used=len(records),
        )

        # 附加感知元数据到 session
        session.perception_metadata = {
            "alarm_count": alarm_count,
            "ne_count": ne_count,
            "severity_counts": severity_counts,
        }

        return summary
