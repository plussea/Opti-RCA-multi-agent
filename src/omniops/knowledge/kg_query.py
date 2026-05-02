"""知识图谱查询服务 — 诊断 Agent 专用"""
import logging
from typing import Any, Dict, List, Optional

from omniops.knowledge.entity_parser import extract_seed_entities
from omniops.knowledge.neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

# 默认嵌入维度（用于兼容未来 Qdrant）
DEFAULT_EMBED_DIM = 1536


class KGQueryService:
    """诊断 Agent 调用 KG 查询的统一接口"""

    def __init__(self, domain: str = "optical_network") -> None:
        self._domain = domain
        self._client = get_neo4j_client()

    async def query(
        self,
        structured_data: List[Any],
        hops: int = 2,
        include_community_summary: bool = True,
        include_rules: bool = True,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        对当前告警会话执行 KG 查询，返回子图+社区摘要+规则

        Args:
            structured_data: Session.structured_data (List[AlarmRecord])
            hops: 子图跳数（默认2跳）
            include_community_summary: 是否返回社区摘要
            include_rules: 是否返回匹配规则

        Returns:
            {
                "subgraph_paths": [...],
                "community_summaries": [...],
                "rules": [...],
                "query_latency_ms": 320,
                "fallback": False,
            }
        """
        import time
        t0 = time.monotonic()

        # 1. 提取种子实体
        alarm_codes = [r.alarm_code for r in structured_data if r.alarm_code]
        alarm_names = [r.alarm_name for r in structured_data if r.alarm_name]
        seed_entities = extract_seed_entities(alarm_codes, alarm_names)

        if not seed_entities:
            logger.warning(f"[KGQuery] No seed entities for session")
            return self._empty_result(0)

        # 2. 子图查询
        subgraph = {"nodes": [], "edges": []}
        try:
            await self._client.connect()
            subgraph_raw = await self._client.query_subgraph(
                seed_entities=seed_entities,
                hops=hops,
                relation_types=["IS_CAUSED_BY", "TRIGGERS", "IS_LOCATED_AT"],
            )
            subgraph["nodes"] = subgraph_raw.get("nodes", [])
            subgraph["edges"] = subgraph_raw.get("edges", [])
        except Exception as e:
            logger.warning(f"[KGQuery] subgraph query failed: {e}")

        # 3. 社区摘要
        community_summaries: List[Dict[str, Any]] = []
        if include_community_summary:
            try:
                summaries = await self._client.get_community_summaries(self._domain)
                # 取 top-k 相关社区
                community_summaries = summaries[:top_k]
            except Exception as e:
                logger.warning(f"[KGQuery] community summaries failed: {e}")

        # 4. 规则匹配
        rules: List[Dict[str, Any]] = []
        if include_rules and alarm_codes:
            try:
                rules = await self._client.get_rules(alarm_codes)
            except Exception as e:
                logger.warning(f"[KGQuery] rules query failed: {e}")

        latency = int((time.monotonic() - t0) * 1000)

        # 5. 路径格式化：子图边转为自然语言路径描述
        paths = self._format_paths(subgraph)

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

    def _format_paths(self, subgraph: Dict[str, Any]) -> List[str]:
        """将子图边转为自然语言路径描述"""
        paths: List[str] = []
        for edge in subgraph.get("edges", []):
            src = edge.get("source", "?")
            rel = edge.get("type", "?")
            tgt = edge.get("target", "?")
            paths.append(f"{src} --[{rel}]--> {tgt}")
        return paths

    def _empty_result(self, latency: int) -> Dict[str, Any]:
        return {
            "subgraph_paths": [],
            "community_summaries": [],
            "rules": [],
            "query_latency_ms": latency,
            "fallback": True,
            "seed_entities": [],
            "subgraph_stats": {"nodes": 0, "edges": 0},
        }

    async def health_check(self) -> bool:
        """检查 KG 服务是否可用"""
        try:
            await self._client.connect()
            stats = await self._client.get_graph_stats(self._domain)
            return True
        except Exception:
            return False


_kg_service: Optional[KGQueryService] = None


def get_kg_service(domain: str = "optical_network") -> KGQueryService:
    global _kg_service
    if _kg_service is None:
        _kg_service = KGQueryService(domain=domain)
    return _kg_service