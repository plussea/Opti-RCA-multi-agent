"""图谱构建器 — 将解析后的节点/关系写入 Neo4j"""
import logging
from typing import Any, Dict, List, Optional

from omniops.knowledge.entity_parser import normalize_entity
from omniops.knowledge.neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


def _infer_label(entity: str) -> str:
    """从实体名称推断节点标签"""
    name_upper = entity.upper()
    if any(k in name_upper for k in ["ALARM", "LOS", "RDI", "PWR", "FEC", "BD", "COMM"]):
        return "Alarm"
    if any(k in name_upper for k in ["FAULT", "断纤", "断裂", "衰减", "污损"]):
        return "Fault"
    if any(k in name_upper for k in ["OTU", "OLP", "AMP", "光放", "板"]):
        return "Device"
    return "Alarm"  # 默认为 Alarm


class GraphBuilder:
    """将实体/关系数据批量写入 Neo4j"""

    def __init__(self) -> None:
        self._client = get_neo4j_client()
        self._stats = {"nodes": 0, "relations": 0, "communities": 0}

    async def build_from_parsed(self, parsed: Dict[str, Any], domain: str = "optical_network") -> Dict[str, int]:
        """从解析结果构建图谱"""
        await self._client.ensure_constraints()

        for node in parsed.get("nodes", []):
            label = node.get("label", "Alarm")
            pk = node.get("primary_key", "code")
            pk_val = node.get(pk, node.get("name", "unknown"))

            # 移除元数据字段
            props = {k: v for k, v in node.items() if k not in ("label", "primary_key", "domain")}
            props["domain"] = node.get("domain", domain)

            try:
                await self._client.merge_node(label, pk, pk_val, props)
                self._stats["nodes"] += 1
            except Exception as e:
                logger.warning(f"Failed to merge node {pk_val}: {e}")

        # 自动生成 Fault.common_alarms → IS_CAUSED_BY 关系（边界修正）
        for node in parsed.get("nodes", []):
            if node.get("label") == "Fault" and node.get("common_alarms"):
                fault_id = node.get("id", node.get("name"))
                for alarm_name in node["common_alarms"]:
                    src = normalize_entity(alarm_name)
                    if src and fault_id:
                        relations.append({
                            "src": src,
                            "tgt": fault_id,
                            "rel": "IS_CAUSED_BY",
                            "confidence": 0.85,
                            "source": f"{fault_id} 的 common_alarms",
                            "domain": domain,
                        })

        for rel in parsed.get("relations", []):
            src = rel.get("src", "")
            tgt = rel.get("tgt", "")
            rel_type = rel.get("rel", "IS_CAUSED_BY")

            if not src or not tgt:
                continue

            # 推断节点标签
            src_label = _infer_label(src)
            tgt_label = _infer_label(tgt)

            props = {k: v for k, v in rel.items() if k not in ("src", "tgt", "rel", "domain")}
            props["domain"] = rel.get("domain", domain)

            try:
                await self._client.merge_relation(
                    src_label, "name", src,
                    tgt_label, "name", tgt,
                    rel_type, props,
                )
                self._stats["relations"] += 1
            except Exception as e:
                logger.warning(f"Failed to merge relation {src}->{tgt}: {e}")

        return self._stats.copy()

    async def run_community_detection(self, domain: str = "optical_network") -> List[Dict[str, Any]]:
        """运行 Louvain 社区检测（通过 Cypher 计算简单连通分量）"""
        from collections import defaultdict

        await self._client.connect()

        # 获取所有 Alarm 和 Fault 节点
        cql = """
        MATCH (n) WHERE n.domain = $domain
        AND (n:Alarm OR n:Fault OR n:Device)
        RETURN n.code as code, n.id as id, n.name as name, labels(n)[0] as label
        """
        async with self._client._driver.session(database="neo4j") as session:  # type: ignore[attr-defined]
            result = await session.run(cql, domain=domain)
            raw_nodes = await result.data()

        if not raw_nodes:
            return []

        # 构建邻接表（基于 IS_CAUSED_BY 和 TRIGGERS 关系）
        edges_cql = """
        MATCH (a)-[r:IS_CAUSED_BY|TRIGGERS]->(b)
        WHERE a.domain = $domain AND b.domain = $domain
        RETURN a.name as src, b.name as tgt
        """
        async with self._client._driver.session(database="neo4j") as session:
            result = await session.run(edges_cql, domain=domain)
            raw_edges = await result.data()

        # Union-Find 找连通分量
        parent: Dict[str, str] = {}
        def find(x: str) -> str:
            if x not in parent:
                parent[x] = x
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x: str, y: str) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[min(rx, ry)] = max(rx, ry)

        node_ids = []
        for n in raw_nodes:
            nid = n.get("name") or n.get("id")
            if nid:
                node_ids.append(nid)

        for e in raw_edges:
            union(e["src"], e["tgt"])

        groups: Dict[str, List[str]] = defaultdict(list)
        for nid in node_ids:
            groups[find(nid)].append(nid)

        communities = []
        for i, (_, members) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))):
            cid = f"c_{domain}_{i+1:02d}"
            community_node = {
                "community_id": cid,
                "name": f"社区{i+1}",
                "summary": f"包含 {', '.join(members[:5])}{' 等' if len(members) > 5 else ''}",
                "keywords": members[:5],
                "node_count": len(members),
                "domain": domain,
            }
            try:
                await self._client.merge_node("Community", "community_id", cid, community_node)
                self._stats["communities"] += 1
                # 社区归属关系
                for member in members:
                    await self._client.merge_relation(
                        "Alarm", "name", member,
                        "Community", "community_id", cid,
                        "BELONGS_TO", {"centrality": 0.5},
                    )
                    await self._client.merge_relation(
                        "Fault", "name", member,
                        "Community", "community_id", cid,
                        "BELONGS_TO", {"centrality": 0.5},
                    )
            except Exception as e:
                logger.warning(f"Community detection error: {e}")
            communities.append(community_node)

        return communities

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()