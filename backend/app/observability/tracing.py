"""轻量级运行时追踪：为每次 Agent 执行记录 span 时间线（LLM/工具/检索步骤）。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def _ms() -> int:
    return int(time.perf_counter() * 1000)


@dataclass
class Span:
    type: str                 # llm | tool | retrieval | pipeline_step
    name: str
    detail: str = ""
    meta: dict = field(default_factory=dict)
    start_ms: int = field(default_factory=_ms)
    end_ms: int | None = None
    elapsed_ms: int = 0
    status: str = "ok"

    def finish(self, detail: str = "", status: str = "ok", meta: dict | None = None) -> None:
        self.end_ms = _ms()
        self.elapsed_ms = self.end_ms - self.start_ms
        self.status = status
        if detail:
            self.detail = detail
        if meta:
            self.meta = {**self.meta, **meta}

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "name": self.name,
            "detail": self.detail[:800],
            "meta": self.meta,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "elapsed_ms": self.elapsed_ms,
            "status": self.status,
        }


class SpanList(list):
    """带自动序号的 span 收集器。"""

    def new(self, *args: Any, **kwargs: Any) -> Span:
        span = Span(*args, **kwargs)
        self.append(span)
        return span

    def to_list(self) -> list[dict]:
        return [s.to_dict() for s in self]


def merge_usage(total: dict, usage: dict) -> dict:
    """累加不同口径的 token usage 字段。"""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in usage:
            total[key] = total.get(key, 0) + int(usage.get(key) or 0)
    return total
