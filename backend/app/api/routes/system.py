"""系统接口：健康检查、指标、工具清单、图表产物。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import verify_auth
from app.config import get_settings
from app.db.models import Artifact
from app.db.session import get_db
from app.tools.registry import list_tools

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(verify_auth)])


@router.get("/health")
def health():
    return {"status": "ok", "app": get_settings().app_name, "version": get_settings().version}


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    settings = get_settings()
    from app.db.models import Agent, Chunk, Dataset, Run

    llm_mode = "mock" if settings.llm_provider != "openai_compatible" or not settings.llm_api_key else "openai_compatible"
    return {
        "llm_provider": llm_mode,
        "llm_model": settings.llm_model,
        "embedding_provider": settings.embedding_provider if settings.embedding_provider == "openai_compatible" and settings.embedding_api_key else "local",
        "agents": db.query(Agent).count(),
        "datasets": db.query(Dataset).count(),
        "chunks": db.query(Chunk).count(),
        "runs": db.query(Run).count(),
        "auth_enabled": settings.auth_enabled,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "net_tools_enabled": settings.net_tools_enabled,
    }


@router.get("/tools")
def tools_list():
    return {
        "items": [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in list_tools()
        ]
    }


@router.get("/artifacts")
def artifacts(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.query(Artifact).order_by(desc(Artifact.created_at)).limit(limit).all()
    return {
        "items": [
            {"id": a.id, "run_id": a.run_id, "kind": a.kind, "path": a.path,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in rows
        ]
    }
