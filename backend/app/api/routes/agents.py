"""Agent 管理：CRUD + 模板。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import verify_auth
from app.api.schemas import AgentCreate, AgentUpdate
from app.agents.templates import TEMPLATES
from app.db.models import Agent
from app.db.session import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(verify_auth)])


def serialize(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "emoji": agent.emoji,
        "description": agent.description,
        "agent_type": agent.agent_type,
        "system_prompt": agent.system_prompt,
        "tools": agent.tools or [],
        "dataset_ids": agent.dataset_ids or [],
        "llm_config": agent.llm_config or {},
        "memory_config": agent.memory_config or {},
        "pipeline": agent.pipeline or [],
        "max_iterations": agent.max_iterations,
        "enabled": agent.enabled,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.created_at).all()
    return {"items": [serialize(a) for a in agents]}


@router.get("/templates")
def list_templates():
    return {"items": TEMPLATES}


@router.post("")
def create_agent(body: AgentCreate, db: Session = Depends(get_db)):
    if body.agent_type not in ("react", "pipeline"):
        raise HTTPException(400, "agent_type 必须是 react 或 pipeline")
    agent = Agent(**body.model_dump())
    db.add(agent)
    db.commit()
    return serialize(agent)


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    return serialize(agent)


@router.put("/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    db.commit()
    return serialize(agent)


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    db.delete(agent)
    db.commit()
    return {"ok": True}
