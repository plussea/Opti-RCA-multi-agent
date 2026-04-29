"""影响 Agent"""
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.models import CognitiveSummary, Impact, Session


class ImpactAgent(BaseAgent):
    """影响 Agent：评估故障影响范围"""

    name = "impact"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """评估影响范围"""
        diagnosis = session.diagnosis_result
        records = session.structured_data

        # 提取告警网元列表
        affected_ne: List[str] = []
        for r in records:
            if r.ne_name and r.ne_name not in affected_ne:
                affected_ne.append(r.ne_name)

        # 基于根因和网元评估影响（简化版，依赖拓扑知识库）
        # TODO: 后续接入 Neo4j 拓扑查询
        affected_links: List[str] = []
        affected_services: List[str] = []

        root_cause = diagnosis.root_cause if diagnosis else "未知"
        confidence = diagnosis.confidence if diagnosis else 0.0

        if "光链路" in root_cause or "光纤" in root_cause:
            # 光链路故障通常影响 1-2 条骨干链路
            for ne in affected_ne:
                affected_links.append(f"{ne}-UPLINK-01")
            affected_services.append("骨干传输业务")

        elif "电源" in root_cause:
            # 电源故障可能影响整个站点
            for ne in affected_ne:
                affected_links.extend([f"{ne}-UPLINK-0{i}" for i in range(1, 3)])
            affected_services.append("站点全部业务")

        elif "板卡" in root_cause:
            # 板卡故障影响对应链路
            for ne in affected_ne:
                affected_links.append(f"{ne}-BOARD-SLOT")
            affected_services.append("单板承载业务")

        else:
            # 默认：仅告警网元本身
            for ne in affected_ne:
                affected_links.append(f"{ne}-LOCAL")

        session.impact = Impact(
            affected_links=affected_links,
            affected_services=affected_services,
            affected_ne=affected_ne,
        )

        evidence_list: List[Dict[str, Any]] = [
            {"type": "affected_ne", "source": ne}
            for ne in affected_ne
        ]

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="planning",
            session_id=session.session_id,
            conclusion=(
                f"影响评估：{len(affected_ne)} 个网元、"
                f"{len(affected_links)} 条链路、"
                f"{len(affected_services)} 类业务受影响"
            ),
            confidence=confidence,
            evidence=evidence_list,
            uncertainty=None,
            required_action="基于影响范围生成修复方案",
            context_window_used=len(records),
        )
