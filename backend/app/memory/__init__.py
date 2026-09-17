"""会话记忆：从数据库加载历史消息并按窗口截断。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Message


def load_history(db: Session, conversation_id: str, window: int) -> list[dict]:
    """取最近 window 条 user/assistant 消息，按时间正序返回 OpenAI 消息格式。"""
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(window)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]
