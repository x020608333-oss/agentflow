"""AgentFlow 应用入口：装配网关中间件、路由、静态资源。"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import agents, chat, conversations, datasets, runs, system
from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.gateway import RateLimitMiddleware, RequestLogMiddleware
from app.db.session import get_engine

# 导入 tools.handlers 完成工具注册
import app.tools.handlers  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_dirs()
    get_engine()  # 启动时建表

    if not settings.auth_enabled and settings.host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger("agentflow").warning(
            "鉴权关闭且监听 %s：python_exec/联网工具不应暴露到公网。"
            "请设置 AGENTFLOW_AUTH_ENABLED=true 并配置 API Key。",
            settings.host,
        )

    app = FastAPI(title=settings.app_name, version=settings.version,
                  description="AgentFlow —— 企业级 AI Agent 工作平台")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)

    install_error_handlers(app)

    app.include_router(system.router)
    app.include_router(agents.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(datasets.router)
    app.include_router(runs.router)

    # 静态资源：前端 SPA + 图表/上传文件
    app.mount("/files/charts", StaticFiles(directory=str(settings.charts_dir)), name="charts")
    app.mount("/assets", StaticFiles(directory=str(settings.frontend_dir / "assets")), name="assets")
    app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
