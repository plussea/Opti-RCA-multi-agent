"""影响 Agent — 基于拓扑图推理影响范围"""
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.core.topology_manager import (
    get_adjacent_edges,
    get_neighbors,
    get_topology_type,
)
from omniops.models import CognitiveSummary, Impact, Session


class ImpactAgent(BaseAgent):
    """影响 Agent：基于拓扑图评估故障影响范围"""

    name = "impact"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """评估影响范围"""
        records = session.structured_data
        diagnosis = session.diagnosis_result

        # 收集告警网元（去重）
        alarm_ne_names: List[str] = []
        for r in records:
            if r.ne_name and r.ne_name not in alarm_ne_names:
                alarm_ne_names.append(r.ne_name)

        if not alarm_ne_names:
            session.impact = Impact(affected_ne=[], affected_links=[], affected_services=[])
            return CognitiveSummary(
                from_agent=self.name,
                to_agent="planning",
                session_id=session.session_id,
                conclusion="影响评估：无告警网元数据",
                confidence=1.0,
                evidence=[],
                uncertainty=None,
                required_action="生成修复方案",
                context_window_used=0,
            )

        # 确定拓扑 ID（从告警记录中取第一个非空的）
        topology_id: Optional[str] = None
        for r in records:
            if r.topology_id:
                topology_id = r.topology_id
                break
        if topology_id is None:
            topology_id = context.get("topology_id") if context else None

        # 拓扑感知的影响评估
        if topology_id:
            affected_links = get_adjacent_edges(topology_id, alarm_ne_names)
            affected_services = _derive_services(topology_id, alarm_ne_names)
        else:
            # 无拓扑信息时的降级策略
            affected_links = [f"{ne}-LOCAL" for ne in alarm_ne_names]
            affected_services = ["未知业务"]

        session.impact = Impact(
            affected_links=affected_links,
            affected_services=affected_services,
            affected_ne=alarm_ne_names,
        )

        # 生成拓扑感知证据
        evidence_list: List[Dict[str, Any]] = []
        for ne in alarm_ne_names:
            if topology_id:
                nbrs = get_neighbors(topology_id, ne)
                degree = len(nbrs)
                evidence_list.append({
                    "type": "affected_ne",
                    "source": ne,
                    "value": f"degree={degree}, neighbors={nbrs}",
                })
            else:
                evidence_list.append({"type": "affected_ne", "source": ne})

        confidence = diagnosis.confidence if diagnosis else 0.0

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="planning",
            session_id=session.session_id,
            conclusion=(
                f"影响评估：{len(alarm_ne_names)} 个网元、"
                f"{len(affected_links)} 条链路、"
                f"{len(affected_services)} 类业务受影响"
            ),
            confidence=confidence,
            evidence=evidence_list,
            uncertainty=None if topology_id else "无拓扑数据，影响范围可能不完整",
            required_action="基于影响范围生成修复方案",
            context_window_used=len(records),
        )


def _derive_services(topo_id: str, alarm_ne_names: List[str]) -> List[str]:
    """根据拓扑类型和告警网元推导受影响的业务类型"""
    topo_type = get_topology_type(topo_id)

    services: List[str] = []
    if topo_type == "MESH":
        services.append("Mesh 骨干传输业务")
        if len(alarm_ne_names) >= 3:
            services.append("多路径调度业务")
    elif topo_type == "CHAIN":
        services.append("链形接入业务")
        services.append("下游汇聚业务")
    elif topo_type == "RING":
        services.append("环形保护业务")
        services.append("主备倒换业务")

    if not services:
        services.append("光网络传输业务")

    return services
