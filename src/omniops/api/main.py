"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from omniops.api.routes import router
from omniops.core.config import get_settings
from omniops.core.database import close_db, init_db
from omniops.memory.redis_store import get_redis_session_store
from omniops.rag import init_seed_knowledge

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting OmniOps...")
    settings = get_settings()

    # 设置日志级别
    import sys
    from loguru import logger as loguru_logger
    loguru_logger.remove()
    loguru_logger.add(sys.stderr, level=settings.log_level)

    # 初始化数据库
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed (may not be running): {e}")

    # 初始化 Redis
    try:
        redis_store = await get_redis_session_store()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis connection failed (may not be running): {e}")

    # 初始化种子知识库
    try:
        await init_seed_knowledge()
        logger.info("Seed knowledge initialized")
    except Exception as e:
        logger.warning(f"Seed knowledge initialization failed: {e}")

    logger.info(f"OmniOps started on {settings.api_host}:{settings.api_port}")

    yield

    # 关闭时
    logger.info("Shutting down OmniOps...")
    try:
        await close_db()
    except Exception:
        pass
    try:
        redis_store = await get_redis_session_store()
        await redis_store.close()
    except Exception:
        pass
    logger.info("OmniOps shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="OmniOps API",
        description="结构化数据驱动的智能诊断与建议系统",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(router)

    return app


app = create_app()


def main():
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "omniops.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
    )


if __name__ == "__main__":
    main()