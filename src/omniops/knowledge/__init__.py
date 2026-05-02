"""知识图谱模块 — GraphRAG 构建与查询

目录结构：
    neo4j_client.py   — Neo4j 连接与 Cypher 查询
    entity_parser.py  — 实体/关系提取（结构化快速通道 + LLM 回退）
    graph_builder.py — 图谱构建（节点/关系 MERGE）
"""

from omniops.knowledge.neo4j_client import Neo4jClient

__all__ = ["Neo4jClient"]