"""API 网关中间件：结构化请求日志 + 滑动窗口限流。"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("agentflow.gateway")

SKIP_LOG_PATHS = ("/api/health", "/assets", "/files")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
        finally:
            elapsed = int((time.perf_counter() - start) * 1000)
            if not request.url.path.startswith(SKIP_LOG_PATHS):
                logger.info(json.dumps({
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code if response else 500,
                    "elapsed_ms": elapsed,
                    "client": request.client.host if request.client else "",
                }, ensure_ascii=False))
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """每 IP 滑动窗口限流（内存实现，多实例部署时换 Redis 即可）。"""

    def __init__(self, app, per_minute: int = 60):
        super().__init__(app)
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(("/assets", "/files", "/api/health")):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.time()
        window = self._hits[client]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            return JSONResponse(
                {"code": 429, "message": f"请求过于频繁，每分钟最多 {self.per_minute} 次"},
                status_code=429,
            )
        window.append(now)
        return await call_next(request)
