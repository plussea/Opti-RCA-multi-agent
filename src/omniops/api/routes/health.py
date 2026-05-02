"""健康检查路由"""
from fastapi import APIRouter
from sqlalchemy import text
from typing import Any, Dict

from omniops.memory.redis_store import get_redis_session_store

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    health_info: Dict[str, Any] = {
        "status": "healthy",
        "version": "0.1.0",
        "components": {},
    }

    try:
        redis_store = await get_redis_session_store()
        await redis_store.client.ping()
        health_info["components"]["redis"] = "connected"
    except Exception:
        health_info["components"]["redis"] = "disconnected"

    try:
        from omniops.core.database import async_session_maker
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
        health_info["components"]["database"] = "connected"
    except Exception:
        health_info["components"]["database"] = "disconnected"

    try:
        from omniops.rag.chroma_store import get_vector_store
        count = get_vector_store().get_count()
        health_info["components"]["vector_store"] = f"connected ({count} entries)"
    except Exception:
        health_info["components"]["vector_store"] = "disconnected"

    return health_info
