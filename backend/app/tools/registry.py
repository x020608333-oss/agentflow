"""工具注册表：每个工具 = 名称 + 描述 + JSON Schema 参数 + 异步处理器。

Agent Runtime 通过 tool_schemas() 生成 OpenAI function calling 格式，
通过 execute_tool() 统一执行并计时。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.config import Settings


@dataclass
class ToolContext:
    settings: Settings
    default_dataset_ids: list[str] = field(default_factory=list)
    run_id: str | None = None
    # 本次运行产生的产物 (url_path, kind)，运行结束后由 runtime 落库
    artifacts: list = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict, ToolContext], Awaitable[str]]
    enabled: bool = True


REGISTRY: dict[str, ToolSpec] = {}


def register(name: str, description: str, parameters: dict):
    def deco(fn):
        REGISTRY[name] = ToolSpec(name=name, description=description, parameters=parameters, handler=fn)
        return fn

    return deco


def list_tools() -> list[ToolSpec]:
    return [t for t in REGISTRY.values() if t.enabled]


def tool_schemas(names: list[str]) -> list[dict]:
    """生成 OpenAI function calling 的 tools 参数。"""
    schemas = []
    for name in names:
        spec = REGISTRY.get(name)
        if not spec:
            continue
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return schemas


def truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[输出过长已截断，共 {len(text)} 字符]"


async def execute_tool(
    name: str, args: dict, ctx: ToolContext
) -> tuple[bool, str, int]:
    """执行工具，返回 (是否成功, 结果文本, 耗时ms)。超过 tool_timeout 会取消。"""
    spec = REGISTRY.get(name)
    if not spec:
        return False, f"未知工具: {name}", 0
    start = time.perf_counter()
    timeout = getattr(ctx.settings, "tool_timeout", None)
    try:
        result = await asyncio.wait_for(spec.handler(args or {}, ctx), timeout=timeout)
        ok = True
    except asyncio.TimeoutError:
        result = f"工具执行超时（>{timeout}s），已取消"
        ok = False
    except Exception as exc:  # 工具失败不终结 Agent 运行，错误回传给模型自行调整
        result = f"工具执行出错: {type(exc).__name__}: {exc}"
        ok = False
    elapsed = int((time.perf_counter() - start) * 1000)
    return ok, truncate(result), elapsed
