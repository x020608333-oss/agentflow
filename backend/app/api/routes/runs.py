"""运行记录（可观测性）：列表与 trace 详情。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import verify_auth
from app.db.models import Run
from app.db.session import get_db

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(verify_auth)])


@router.get("")
def list_runs(limit: int = 50, agent_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Run)
    if agent_id:
        q = q.filter(Run.agent_id == agent_id)
    items = q.order_by(desc(Run.started_at)).limit(min(limit, 200)).all()
    return {
        "items": [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "agent_name": r.agent_name,
                "agent_type": r.agent_type,
                "status": r.status,
                "input": r.input[:120],
                "duration_ms": r.duration_ms,
                "usage": r.usage or {},
                "tool_calls": len([s for s in (r.spans or []) if s.get("type") == "tool"]),
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in items
        ]
    }


@router.get("/stats")
def run_stats(db: Session = Depends(get_db)):
    """全局指标：总运行数、成功率、平均耗时、token 消耗。"""
    runs = db.query(Run).all()
    total = len(runs)
    ok = sum(1 for r in runs if r.status == "succeeded")
    durations = [r.duration_ms for r in runs if r.duration_ms]
    tokens = sum(int((r.usage or {}).get("completion_tokens", 0)) for r in runs)
    return {
        "total_runs": total,
        "succeeded": ok,
        "success_rate": round(ok / total, 3) if total else None,
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
        "total_completion_tokens": tokens,
    }


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    r = db.get(Run, run_id)
    if not r:
        raise HTTPException(404, "运行记录不存在")
    return {
        "id": r.id,
        "conversation_id": r.conversation_id,
        "agent_id": r.agent_id,
        "agent_name": r.agent_name,
        "agent_type": r.agent_type,
        "status": r.status,
        "input": r.input,
        "output": r.output,
        "error": r.error,
        "spans": r.spans or [],
        "usage": r.usage or {},
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "duration_ms": r.duration_ms,
    }
