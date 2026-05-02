"""Neo4j 图数据库客户端"""
import logging
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase
from neo4j.api import Bookmarks

from omniops.core.config import get_settings

logger = logging.getLogger(__name__)

# Neo4j 节点标签
LABEL_ALARM = "Alarm"
LABEL_FAULT = "Fault"
LABEL_DEVICE = "Device"
LABEL_TOPOLOGY = "Topology"
LABEL_RULE = "Rule"
LABEL_COMMUNITY = "Community"

# 关系类型
REL_IS_CAUSED_BY = "IS_CAUSED_BY"
REL_TRIGGERS = "TRIGGERS"
REL_IS_LOCATED_AT = "IS_LOCATED_AT"
REL_CONNECTED_UPSTREAM = "CONNECTED_UPSTREAM"
REL_BELONGS_TO_LINK = "BELONGS_TO_LINK"
REL_HAS_ALERT = "HAS_ALERT"
REL_BELONGS_TO = "BELONGS_TO"
REL_APPLIES_TO = "APPLIES_TO"
REL_NEXT_STEP = "NEXT_STEP"

REL_TYPES = {
    REL_IS_CAUSED_BY,
    REL_TRIGGERS,
    REL_IS_LOCATED_AT,
    REL_CONNECTED_UPSTREAM,
    REL_BELONGS_TO_LINK,
    REL_HAS_ALERT,
    REL_BELONGS_TO,
    REL_APPLIES_TO,
    REL_NEXT_STEP,
}


class Neo4jClient:
    """Neo4j 图数据库异步客户端"""

    def __init__(self, domain: str = "optical_network") -> None:
        settings = get_settings()
        self._uri = settings.neo4j_uri
        self._auth = (settings.neo4j_user, settings.neo4j_password)
        self._driver: Optional[Any] = None
        self._domain = domain

    async def connect(self) -> None:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=self._auth,
                max_connection_lifetime=3600,
            )
            logger.info(f"Neo4j connected to {self._uri}")

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def ensure_constraints(self) -> None:
        """创建唯一性约束（幂等）"""
        constraints = [
            "CREATE CONSTRAINT alarm_name IF NOT EXISTS FOR (a:Alarm) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT fault_id IF NOT EXISTS FOR (f:Fault) REQUIRE f.id IS UNIQUE",
            "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT link_id IF NOT EXISTS FOR (t:Topology) REQUIRE t.link_id IS UNIQUE",
            "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.rule_id IS UNIQUE",
            "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.community_id IS UNIQUE",
        ]
        await self.connect()
        async with self._driver.session(database="neo4j") as session:
            for cql in constraints:
                try:
                    await session.run(cql)
                except Exception:
                    pass  # 约束已存在

    async def merge_node(
        self,
        label: str,
        primary_key: str,
        primary_value: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """MERGE 一个节点，返回其属性"""
        await self.connect()
        props = properties or {}
        props_str = ", ".join([f"k: '{k}', v: $p_{k}" for k in props])
        cql = f"""
        MERGE (n:{label} {{{primary_key}: $pk}})
        ON CREATE SET n += $props
        ON MATCH SET n += $props
        RETURN n.{primary_key} as pk
        """
        async with self._driver.session(database="neo4j") as session:
            params = {"pk": primary_value, "props": props}
            for k, v in props.items():
                params[f"p_{k}"] = v
            result = await session.run(cql, **params)
            records = await result.data()
            return {"pk": primary_value, **props} if records else props

    async def merge_relation(
        self,
        src_label: str,
        src_pk: str,
        src_val: str,
        tgt_label: str,
        tgt_pk: str,
        tgt_val: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """MERGE 一条关系"""
        await self.connect()
        props = properties or {}
        props_clause = ", ".join([f"r.{k} = $p_{k}" for k in props]) if props else ""
        cql = f"""
        MATCH (src:{src_label} {{{src_pk}: $src_val}})
        MATCH (tgt:{tgt_label} {{{tgt_pk}: $tgt_val}})
        MERGE (src)-[r:{rel_type}]->(tgt)
        {'SET ' + props_clause if props_clause else ''}
        """
        params = {"src_val": src_val, "tgt_val": tgt_val}
        for k, v in props.items():
            params[f"p_{k}"] = v
        async with self._driver.session(database="neo4j") as session:
            await session.run(cql, **params)

    async def query_subgraph(
        self,
        seed_entities: List[str],
        hops: int = 2,
        relation_types: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """查询以种子实体为中心的子图"""
        await self.connect()

        label_filter = ""
        if labels:
            label_filter = f"AND any(label IN labels(n) WHERE label IN {labels})"

        # Filter on relationship list inside path: any(rel IN r WHERE type(rel) IN $rel_types)
        # $rel_types is only set when relation_types is provided (otherwise we skip the filter)
        rel_where = ""
        if relation_types:
            rel_where = f"WHERE any(rel IN r WHERE type(rel) IN $rel_types)"

        cql = f"""
        MATCH (start)
        WHERE any(prop IN ['code', 'id', 'name'] WHERE start[prop] IN $seeds)
        {label_filter}
        MATCH path = (start)-[r*1..{hops}]-(neighbor)
        {rel_where}
        WITH DISTINCT start, neighbor, r
        WITH collect(DISTINCT start) + collect(DISTINCT neighbor) as raw_nodes, collect(DISTINCT r) as raw_rels
        UNWIND raw_nodes as n
        WITH DISTINCT n as node, raw_rels
        UNWIND raw_rels as rels_path
        UNWIND rels_path as rel
        WITH collect(DISTINCT node) as nodes_list, collect(DISTINCT rel) as rels_list
        RETURN
            [n IN nodes_list | {{id: coalesce(n.code, n.id, n.name), label: labels(n)[0], name: n.name, props: n}}] as nodes,
            [rel IN rels_list | {{source: coalesce(startNode(rel).code, startNode(rel).id, startNode(rel).name), target: coalesce(endNode(rel).code, endNode(rel).id, endNode(rel).name), type: type(rel)}}] as edges
        """
        params: Dict[str, Any] = {"seeds": seed_entities}
        if relation_types:
            params["rel_types"] = relation_types
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(cql, **params)
            records = await result.data()
            return records[0] if records else {"nodes": [], "edges": []}

    async def find_paths(
        self,
        from_entity: str,
        to_entity: str,
        max_depth: int = 4,
    ) -> List[Dict[str, Any]]:
        """查找两个实体之间的路径"""
        await self.connect()
        cql = """
        MATCH path = (a)-[:IS_CAUSED_BY|TRIGGERS*1..4]-(b)
        WHERE (any(prop IN ['code', 'id', 'name'] WHERE a[prop] = $from_ent) AND
               any(prop IN ['code', 'id', 'name'] WHERE b[prop] = $to_ent))
        RETURN path, length(path) as depth
        ORDER BY depth ASC
        LIMIT 5
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(cql, from_ent=from_entity, to_ent=to_entity)
            records = await result.data()
            return [{"path": str(r["path"]), "depth": r["depth"]} for r in records]

    async def get_community_summaries(self, domain: str = "optical_network") -> List[Dict[str, Any]]:
        """获取所有社区摘要"""
        await self.connect()
        cql = """
        MATCH (c:Community)
        WHERE c.domain = $domain OR $domain = 'all'
        RETURN c.community_id as community_id, c.name as name, c.summary as summary,
               c.keywords as keywords, c.node_count as node_count
        ORDER BY c.node_count DESC
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(cql, domain=domain)
            return await result.data()

    async def get_rules(self, alarm_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取告警相关规则"""
        await self.connect()
        if alarm_names:
            cql = """
            MATCH (r:Rule)-[:IS_CAUSED_BY|TRIGGERS]->(a:Alarm)
            WHERE a.name IN $names
            RETURN r.rule_id as rule_id, r.name as name,
                   coalesce(r.content, r.description, '') as content
            """
            params = {"names": alarm_names}
        else:
            cql = """
            MATCH (r:Rule)
            RETURN r.rule_id as rule_id, r.name as name,
                   coalesce(r.content, r.description, '') as content
            """
            params = {}
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(cql, **params)
            return await result.data()

    async def get_graph_stats(self, domain: str = "optical_network") -> Dict[str, int]:
        """获取图谱统计信息"""
        await self.connect()
        cql = """
        MATCH (n)
        RETURN labels(n)[0] as label, count(n) as count
        UNION ALL
        MATCH ()-[r]->()
        RETURN 'edges' as label, count(r) as count
        """
        async with self._driver.session(database="neo4j") as session:
            result = await session.run(cql)
            records = await result.data()
            stats = {"nodes": 0, "edges": 0}
            for r in records:
                if r["label"] == "edges":
                    stats["edges"] = r["count"]
                else:
                    stats["nodes"] += r["count"]
            return stats

    async def clear_domain(self, domain: str) -> None:
        """删除指定领域的全部数据"""
        await self.connect()
        cql = """
        MATCH (n)
        WHERE n.domain = $domain
        DETACH DELETE n
        """
        async with self._driver.session(database="neo4j") as session:
            await session.run(cql, domain=domain)

    async def query_session(
        self,
        structured_data: Optional[List[Any]] = None,
        seed_entities: Optional[List[str]] = None,
        hops: int = 2,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """查询诊断会话的子图+社区摘要+规则（供 DiagnosisAgent 使用）

        等同于 KGQueryService.query()，但直接内联在 Neo4jClient 中，
        消除不必要的浅层适配器。
        """
        import time
        from omniops.knowledge.entity_parser import extract_seed_entities

        t0 = time.monotonic()

        if seed_entities is None:
            alarm_names = [r.alarm_name for r in (structured_data or []) if r.alarm_name]
            seed_entities = extract_seed_entities(alarm_names)

        if not seed_entities:
            return self._empty_session_result(0)

        subgraph = {"nodes": [], "edges": []}
        try:
            await self.connect()
            subgraph_raw = await self.query_subgraph(
                seed_entities=seed_entities,
                hops=hops,
                relation_types=["IS_CAUSED_BY", "TRIGGERS", "IS_LOCATED_AT"],
            )
            subgraph["nodes"] = subgraph_raw.get("nodes", [])
            subgraph["edges"] = subgraph_raw.get("edges", [])
        except Exception as e:
            logger.warning(f"[Neo4jClient] subgraph query failed: {e}")

        community_summaries: List[Dict[str, Any]] = []
        try:
            await self.connect()
            summaries = await self.get_community_summaries(self._domain)
            community_summaries = summaries[:top_k]
        except Exception as e:
            logger.warning(f"[Neo4jClient] community summaries failed: {e}")

        rules: List[Dict[str, Any]] = []
        if alarm_names:
            try:
                await self.connect()
                rules = await self.get_rules(alarm_names)
            except Exception as e:
                logger.warning(f"[Neo4jClient] rules query failed: {e}")

        latency = int((time.monotonic() - t0) * 1000)
        paths = [f"{e.get('source','?')} --[{e.get('type','?')}]--> {e.get('target','?')}"
                 for e in subgraph.get("edges", [])]

        return {
            "subgraph_paths": paths,
            "community_summaries": community_summaries,
            "rules": rules[:top_k],
            "query_latency_ms": latency,
            "fallback": False,
            "seed_entities": seed_entities[:10],
            "subgraph_stats": {
                "nodes": len(subgraph["nodes"]),
                "edges": len(subgraph["edges"]),
            },
        }

    def _empty_session_result(self, latency: int) -> Dict[str, Any]:
        return {
            "subgraph_paths": [],
            "community_summaries": [],
            "rules": [],
            "query_latency_ms": latency,
            "fallback": True,
            "seed_entities": [],
            "subgraph_stats": {"nodes": 0, "edges": 0},
        }


# 全局单例
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client