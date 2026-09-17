"""LLM 统一抽象层。

- OpenAICompatibleProvider: 任何 OpenAI 兼容接口（智谱/DeepSeek/通义/OpenAI...），支持原生 function calling。
- MockProvider: 内置离线模拟模型，按关键词脚本化返回工具调用与回答，
  使项目在没有任何 API Key 时也能完整演示 ReAct 循环与全部工具链路。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class LLMResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"


def _estimate_usage(text: str) -> dict:
    # 粗略估算：中文约 1 字符 1 token，英文约 4 字符 1 token
    return {"prompt_tokens": 0, "completion_tokens": max(1, len(text) // 2)}


class BaseProvider:
    name = "base"

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseProvider):
    name = "openai_compatible"

    def __init__(self, settings: Settings):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.default_model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.timeout = settings.llm_timeout

    async def chat(self, messages, tools=None, model=None, temperature=None, max_tokens=None):
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = [
            ToolCall(
                id=tc.get("id", f"call_{i}"),
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"].get("arguments") or "{}"),
            )
            for i, tc in enumerate(msg.get("tool_calls") or [])
        ]
        return LLMResult(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=data.get("usage") or {},
            finish_reason=choice.get("finish_reason", "stop"),
        )


class MockProvider(BaseProvider):
    """离线模拟模型。

    脚本化策略：
    1. 对话中尚无工具结果且本调用允许工具时 -> 返回一个与可用工具匹配的模拟工具调用；
    2. 否则 -> 返回引用检索上下文/工具结果的确定性回答。
    """

    name = "mock"

    def __init__(self, settings: Settings):
        self.temperature = settings.llm_temperature

    async def chat(self, messages, tools=None, model=None, temperature=None, max_tokens=None):
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )

        if tools and not has_tool_result:
            call = self._scripted_tool_call(tools, last_user)
            if call:
                return LLMResult(
                    content=f"我需要先调用工具收集信息，然后再回答你的问题。",
                    tool_calls=[call],
                    usage=_estimate_usage(last_user),
                    finish_reason="tool_calls",
                )

        content = self._final_answer(messages, last_user)
        return LLMResult(
            content=content,
            usage=_estimate_usage(content),
            finish_reason="stop",
        )

    def _scripted_tool_call(self, tools: list[dict], user_text: str) -> ToolCall | None:
        available = [t["function"]["name"] for t in tools]
        # 用户要求画图且可用时，优先演示 python_exec + 图表自动保存链路
        if "python_exec" in available and any(k in user_text for k in ("图", "chart", "画")):
            code = (
                "import matplotlib.pyplot as plt\n"
                "import sqlite3, pandas as pd\n"
                "con = sqlite3.connect(DB_PATH)\n"
                "tables = [r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
                "print('可用表:', tables)\n"
                "fig, ax = plt.subplots(figsize=(6, 3.4))\n"
                "ax.bar(['华东', '华南', '华北', '西南', '东北'], [26.4, 21.8, 19.5, 17.2, 15.1], color='#6c5ce7')\n"
                "ax.set_title('各地区销售额（万元）- Mock 演示数据')\n"
                "ax.spines[['top', 'right']].set_visible(False)\n"
            )
            return ToolCall(id="mock_call_1", name="python_exec", arguments={"code": code})
        # 按优先级选择最贴合"演示叙事"的工具
        for name in ("vector_search", "crm_lookup", "web_search", "sql_query", "python_exec"):
            if name in available:
                break
        else:
            return None
        args: dict = {}
        if name == "vector_search":
            args = {"query": user_text[:60] or "产品介绍"}
        elif name == "web_search":
            args = {"query": user_text[:60] or "行业研究"}
        elif name == "crm_lookup":
            args = {"keyword": user_text[:20] or ""}
        elif name == "sql_query":
            args = {"sql": "SELECT name FROM sqlite_master WHERE type='table' LIMIT 5"}
        elif name == "python_exec":
            args = {"code": "print(sum(range(101)))"}
        return ToolCall(id="mock_call_1", name=name, arguments=args)

    def _final_answer(self, messages: list[dict], user_text: str) -> str:
        # 汇总工具结果 / 检索上下文，生成确定性回答
        tool_outputs = [m["content"] for m in messages if m.get("role") == "tool"]
        ctx_line = ""
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "【参考资料】" in system:
            ctx = system.split("【参考资料】", 1)[1].strip()
            ctx_line = ctx[:400]

        lines = [
            f"（Mock 模式回答）关于「{user_text[:50] or '你的问题'}」",
            "",
        ]
        if tool_outputs:
            preview = tool_outputs[-1][:500]
            lines.append("我调用了工具并获得了以下信息：")
            lines.append("")
            lines.append(f"> {preview}")
            # 图表产物单独列出，避免被截断丢失
            import re as _re

            for m in _re.finditer(r"/files/charts/[\w.-]+", "\n".join(tool_outputs)):
                lines.append("")
                lines.append(f"📊 已生成图表：![chart]({m.group(0)})")
            lines.append("")
        if ctx_line:
            lines.append("结合知识库中的参考资料，可以确认相关要点如上。")
        else:
            lines.append("以上为基于工具返回结果整理的结论。")
        lines.append("")
        lines.append("> 提示：当前使用离线 Mock 模型。配置 AGENTFLOW_LLM_PROVIDER=openai_compatible "
                     "与 API Key 后即可接入真实大模型（智谱/DeepSeek/OpenAI 等兼容接口）。")
        return "\n".join(lines)


_PROVIDER: BaseProvider | None = None


def get_llm_provider(settings: Settings, db: Session | None = None) -> BaseProvider:
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    if settings.llm_provider == "openai_compatible" and settings.llm_api_key:
        _PROVIDER = OpenAICompatibleProvider(settings)
    else:
        _PROVIDER = MockProvider(settings)
    return _PROVIDER


def reset_provider() -> None:
    """测试或配置变更后重置单例。"""
    global _PROVIDER
    _PROVIDER = None
