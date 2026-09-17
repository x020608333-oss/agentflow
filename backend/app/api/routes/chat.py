"""对话接口：SSE 流式 + 同步模式。"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.runtime import run_agent_stream
from app.api.deps import verify_auth
from app.api.schemas import ChatRequest
from app.config import get_settings
from app.db.models import Agent
from app.db.session import get_db

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(verify_auth)])


@router.post("")
async def chat(body: ChatRequest, db: Session = Depends(get_db)):
    agent = db.get(Agent, body.agent_id)
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    if not agent.enabled:
        raise HTTPException(400, "Agent 已停用")
    db.close()  # 流式执行使用独立短连接，避免长时间占用请求级会话

    conversation_id = body.conversation_id or "conv_" + uuid.uuid4().hex[:16]

    if not body.stream:
        # 同步模式：收集全部事件后返回（供测试与简单调用方使用）
        final = {"content": "", "usage": {}, "run_id": "", "events": []}
        async for ev in run_agent_stream(agent, conversation_id, body.message, get_settings()):
            final["events"].append(ev)
            if ev["type"] == "final":
                final.update({"content": ev["content"], "usage": ev["usage"], "run_id": ev["run_id"]})
        return final

    async def sse():
        async for ev in run_agent_stream(agent, conversation_id, body.message, get_settings()):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
