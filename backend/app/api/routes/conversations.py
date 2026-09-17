"""会话与消息查询。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import verify_auth
from app.db.models import Conversation, Message
from app.db.session import get_db

router = APIRouter(prefix="/api/conversations", tags=["conversations"], dependencies=[Depends(verify_auth)])


def _serialize(c: Conversation) -> dict:
    return {
        "id": c.id,
        "agent_id": c.agent_id,
        "title": c.title,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("")
def list_conversations(agent_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Conversation)
    if agent_id:
        q = q.filter(Conversation.agent_id == agent_id)
    items = q.order_by(desc(Conversation.updated_at)).limit(100).all()
    return {"items": [_serialize(c) for c in items]}


@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return {
        "conversation": _serialize(conv),
        "items": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "meta": m.meta or {},
                "run_id": m.run_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ],
    }


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
