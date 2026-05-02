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
        ne_names: set = set()
        alarm_names: set = set()
        topology_ids: set = set()
        severity_counts: Dict[str, int] = {}
        location_count = 0

        for r in records:
            if r.ne_name:
                ne_names.add(r.ne_name)
            if r.alarm_name:
                alarm_names.add(r.alarm_name)
            if r.topology_id:
                topology_ids.add(r.topology_id)
            if r.location:
                location_count += 1
            if r.severity:
                sev = r.severity.value
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

        ne_count = len(ne_names)
        alarm_count = len(records)
        topo_id = next(iter(topology_ids), None)

        # 生成证据列表（前 10 条）
        evidence_list: List[Dict[str, Any]] = [
            {
                "type": "alarm",
                "source": r.ne_name,
                "code": r.alarm_code or r.alarm_name or "unknown",
                "value": r.severity.value if r.severity else "unknown",
                "field": "location",
                "time": r.occur_time.isoformat() if r.occur_time else None,
            }
            for r in records[:10]
        ]

        summary = CognitiveSummary(
            from_agent=self.name,
            to_agent="router",
            session_id=session.session_id,
            conclusion=(
                f"感知完成：提取 {alarm_count} 条告警，来自 {ne_count} 个网元"
                + (f"，拓扑 {topo_id}" if topo_id else "")
            ),
            confidence=1.0,
            evidence=evidence_list,
            uncertainty=None,
            required_action=f"根据 {alarm_count} 条告警进行路由决策",
            context_window_used=len(records),
        )

        # 附加感知元数据（含拓扑 ID，传递给下游 Agent）
        session.perception_metadata = {
            "alarm_count": alarm_count,
            "ne_count": ne_count,
            "severity_counts": severity_counts,
            "topology_id": topo_id,
            "topology_ids": list(topology_ids),
            "alarm_names": list(alarm_names),
            "location_count": location_count,
        }

        # 将拓扑 ID 写入 context，供下游 Agent 查询拓扑
        if context is None:
            context = {}
        if topo_id:
            context["topology_id"] = topo_id

        return summary
