"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from omniops.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="OmniOps API",
        description="结构化数据驱动的智能诊断与建议系统",
        version="0.1.0",
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
    from omniops.core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "omniops.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
    )


if __name__ == "__main__":
    main()
