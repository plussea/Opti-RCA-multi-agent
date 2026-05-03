"""Embedding 向量生成 — 使用 OpenRouter API（OpenAI 兼容格式）"""
import os
from typing import List, Optional

import httpx

from omniops.core.config import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_EMBEDDING_CLIENT: Optional[httpx.AsyncClient] = None


def _get_proxy() -> Optional[str]:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")


def _get_client() -> httpx.AsyncClient:
    global _EMBEDDING_CLIENT
    if _EMBEDDING_CLIENT is None:
        settings = get_settings()
        _EMBEDDING_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {settings.embedding_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://omniops.ai",
                "X-Title": "OmniOps",
            },
            proxy=_get_proxy(),
        )
    return _EMBEDDING_CLIENT


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """调用 OpenRouter embedding 端点，返回归一化向量列表。

    参数:
        texts: 文本列表
    返回:
        List of embedding vectors (same order as input)
    """
    settings = get_settings()
    if not settings.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY not configured")

    client = _get_client()
    response = await client.post(
        f"{OPENROUTER_BASE_URL}/embeddings",
        json={
            "model": settings.embedding_model,
            "input": texts,
        },
        timeout=httpx.Timeout(30.0, connect=10.0),
    )
    response.raise_for_status()
    data = response.json()
    embeddings: List[List[float]] = []
    for item in data["data"]:
        vec = item["embedding"]
        # L2 归一化
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        embeddings.append(vec)
    return embeddings


async def get_embedding(text: str) -> List[float]:
    """返回单个文本的 embedding 向量"""
    results = await get_embeddings([text])
    return results[0]


async def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度（假设已归一化）"""
    return sum(x * y for x, y in zip(a, b))
