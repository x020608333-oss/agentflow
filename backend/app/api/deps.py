"""路由依赖：可选 API Key 鉴权。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.config import get_settings


async def verify_auth(request: Request) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return
    key = request.headers.get("X-API-Key", "")
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key（请求头 X-API-Key）")


AuthDep = Depends(verify_auth)
