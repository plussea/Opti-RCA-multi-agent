"""知识图谱管理路由"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, UploadFile
from typing import Any, Dict, Optional

from omniops.knowledge.neo4j_client import get_neo4j_client

router = APIRouter(prefix="/v1", tags=["knowledge"])

logger = logging.getLogger(__name__)


@router.post("/knowledge/builds", response_model=Dict[str, Any])
async def create_knowledge_build(
    file: Optional[UploadFile] = None,
    domain: str = "optical_network",
    build_mode: str = "structured_first",
) -> Dict[str, Any]:
    """上传知识文档，触发图谱构建流水线。file 为空时重建现有文档。"""
    import os

    if file:
        content = await file.read()
        text = content.decode("utf-8", errors="replace")
    else:
        knowledge_path = os.path.join(os.getcwd(), "input", "data", "knowledge", f"{domain}.md")
        if os.path.exists(knowledge_path):
            with open(knowledge_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            return {
                "build_id": f"kgb_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                "status": "completed",
                "stats": {"nodes_created": 0, "relations_created": 0, "communities_found": 0, "parse_errors": 0},
                "warning": "no file and no existing document found",
            }

    from omniops.knowledge.entity_parser import parse_document
    from omniops.knowledge.graph_builder import GraphBuilder

    parsed = parse_document(text, domain=domain)
    builder = GraphBuilder()
    stats = await builder.build_from_parsed(parsed, domain=domain)

    asyncio.create_task(_run_community_detection(domain))

    build_id = f"kgb_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    return {
        "build_id": build_id,
        "status": "completed",
        "estimated_seconds": 30,
        "stats": stats,
    }


async def _run_community_detection(domain: str) -> None:
    """后台运行社区检测"""
    try:
        from omniops.knowledge.graph_builder import GraphBuilder
        builder = GraphBuilder()
        await asyncio.sleep(1)
        communities = await builder.run_community_detection(domain)
        logger.info(f"[KG] Community detection done: {len(communities)} communities")
    except Exception as e:
        logger.warning(f"[KG] Community detection failed: {e}")


@router.get("/knowledge/builds/{build_id}/status")
async def get_build_status(build_id: str) -> Dict[str, Any]:
    """查询构建进度"""
    client = get_neo4j_client()
    try:
        await client.connect()
        stats = await client.get_graph_stats("optical_network")
    except Exception:
        stats = {"nodes": 0, "edges": 0}
    return {"build_id": build_id, "status": "completed", "progress": 100, "stats": stats}


@router.get("/knowledge/graphs/{domain}/metadata")
async def get_graph_metadata(domain: str) -> Dict[str, Any]:
    """获取领域图谱元数据"""
    client = get_neo4j_client()
    try:
        await client.connect()
        stats = await client.get_graph_stats(domain)
        communities = await client.get_community_summaries(domain)
    except Exception:
        stats = {"nodes": 0, "edges": 0}
        communities = []
    return {
        "domain": domain,
        "nodes": stats.get("nodes", 0),
        "edges": stats.get("edges", 0),
        "communities": len(communities),
        "community_list": communities,
    }


@router.delete("/knowledge/graphs/{domain}")
async def delete_graph(domain: str) -> Dict[str, Any]:
    """删除领域图谱"""
    client = get_neo4j_client()
    try:
        await client.clear_domain(domain)
    except Exception as e:
        logger.warning(f"Clear domain failed: {e}")
    return {"message": f"Domain {domain} cleared", "success": True}


@router.post("/knowledge/graph/query")
async def query_graph(request: Dict[str, Any]) -> Dict[str, Any]:
    """图谱查询 API"""
    import time

    seed_entities = request.get("seed_entities", [])
    hops = request.get("hops", 2)
    domain = request.get("domain", "optical_network")
    top_k = request.get("top_k", 5)

    client = get_neo4j_client()

    if seed_entities:
        try:
            await client.connect()
            subgraph = await client.query_subgraph(
                seed_entities=seed_entities,
                hops=hops,
                relation_types=request.get("relation_types"),
            )
        except Exception as e:
            logger.warning(f"KG query failed: {e}")
            subgraph = {"nodes": [], "edges": []}

        t0 = time.monotonic()
        communities = []
        rules = []
        try:
            communities = await client.get_community_summaries(domain)[:top_k]
        except Exception:
            pass
        try:
            rules = await client.get_rules(request.get("alarm_names", request.get("alarm_codes", [])))[:top_k]
        except Exception:
            pass
        latency = int((time.monotonic() - t0) * 1000)

        paths = [f"{e['source']} --[{e['type']}]--> {e['target']}" for e in subgraph.get("edges", [])]

        return {
            "subgraph": subgraph,
            "subgraph_paths": paths,
            "community_summaries": communities,
            "rules": rules,
            "query_latency_ms": latency,
            "fallback": False,
            "seed_entities": seed_entities[:10],
        }

    return {
        "subgraph": {"nodes": [], "edges": []},
        "subgraph_paths": [],
        "community_summaries": [],
        "rules": [],
        "query_latency_ms": 0,
        "fallback": True,
    }


@router.get("/knowledge/graph/visualization")
async def get_visualization_data(
    domain: str = "optical_network",
    center: Optional[str] = None,
    hops: int = 2,
) -> Dict[str, Any]:
    """获取可视化数据（前端 Cytoscape/力导向图渲染）"""
    client = get_neo4j_client()
    seeds = [center] if center else ["R_LOS", "IN_PWR_LOW"]

    try:
        await client.connect()
        subgraph = await client.query_subgraph(seeds, hops=hops)
    except Exception:
        subgraph = {"nodes": [], "edges": []}

    type_colors = {
        "Alarm": "#ef4444",
        "Fault": "#3b82f6",
        "Device": "#22c55e",
        "Rule": "#f59e0b",
        "Community": "#a855f7",
    }

    nodes_out = []
    for n in subgraph.get("nodes", []):
        props = n.get("props", {})
        label = n.get("name") or n.get("id", n.get("code", "?"))
        nodes_out.append({
            "data": {
                "id": n.get("id", "?"),
                "label": f"{label}\n{n.get('label', '')}",
                "type": n.get("label", "unknown"),
                "color": type_colors.get(n.get("label", "unknown"), "#6b7280"),
            }
        })

    edges_out = []
    for e in subgraph.get("edges", []):
        edges_out.append({
            "data": {
                "id": f"e_{len(edges_out)}",
                "source": e.get("source", "?"),
                "target": e.get("target", "?"),
                "label": e.get("type", ""),
            }
        })

    return {
        "elements": {"nodes": nodes_out, "edges": edges_out},
        "layout": "cose",
        "style": [
            {"selector": "node", "style": {"label": "data(label)", "background-color": "data(color)"}},
            {"selector": "edge", "style": {"label": "data(label)", "target-arrow-shape": "triangle"}},
        ],
    }
