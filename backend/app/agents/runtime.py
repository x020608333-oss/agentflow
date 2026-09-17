"""Agent Runtime：核心执行引擎。

- ReAct 模式：LLM + 原生 function calling 循环调用工具，直至给出最终回答；
- Pipeline 模式：固定步骤编排（检索 -> 分析 -> 交叉验证 -> 报告），每步可有独立工具与提示词；
- 全程产出事件流（thought / tool_call / tool_result / token / artifact ...），
  由 API 层封装为 SSE；同时落库完整 trace（spans + usage）。

说明：LLM 调用采用非流式接口 + 最终回答回放式分片推送（两阶段），
工具轮次与最终回答解耦，实现简单且对 UI 呈现效果一致；直连 token 级流式见 docs/architecture.md 升级路线。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator

from app.config import Settings
from app.db.models import Agent, Artifact, Conversation, Dataset, Message, Run
from app.db.session import get_session_factory
from app.llm.embeddings import get_embedder
from app.llm.provider import BaseProvider, get_llm_provider
from app.memory import load_history
from app.observability.tracing import Span, SpanList, merge_usage
from app.rag.store import vector_store
from app.tools.registry import ToolContext, execute_tool, tool_schemas

PLAYBACK_CHUNK = 24          # 最终回答回放流式的分片大小（字符）
PLAYBACK_DELAY = 0.012
TOOL_RESULT_EVENT_LIMIT = 1500


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _render(template: str, variables: dict) -> str:
    return template.format_map(_SafeDict(**variables))


def _stream_playback(text: str) -> list[str]:
    return [text[i : i + PLAYBACK_CHUNK] for i in range(0, len(text), PLAYBACK_CHUNK)]


def _assistant_tool_call_msg(content: str, tool_calls) -> dict:
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in tool_calls
        ],
    }


async def run_agent_stream(
    agent: Agent,
    conversation_id: str,
    user_message: str,
    settings: Settings,
) -> AsyncIterator[dict]:
    """执行一次 Agent 对话，产出事件流。"""
    started = time.perf_counter()
    provider = get_llm_provider(settings)
    ctx = ToolContext(settings=settings, default_dataset_ids=list(agent.dataset_ids or []))
    spans = SpanList()
    usage: dict = {}
    final_output = ""
    run_id = ""
    db = get_session_factory()()

    try:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            conv = Conversation(id=conversation_id, agent_id=agent.id, title=user_message[:20] or "新对话")
            db.add(conv)
            db.commit()
        elif conv.title in ("", "新对话") and user_message:
            conv.title = user_message[:20]
            db.commit()

        run = Run(
            conversation_id=conversation_id,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_type=agent.agent_type,
            status="running",
            input=user_message,
        )
        db.add(run)
        db.commit()
        run_id = run.id

        db.add(Message(conversation_id=conversation_id, role="user", content=user_message, run_id=run_id))
        db.commit()

        yield {"type": "run_started", "run_id": run_id, "conversation_id": conversation_id,
               "agent": {"id": agent.id, "name": agent.name, "emoji": agent.emoji}}

        window = int((agent.memory_config or {}).get("window", settings.memory_window))
        history = load_history(db, conversation_id, window)
    finally:
        db.close()

    out = {"final": ""}
    try:
        if agent.agent_type == "pipeline":
            async for ev in _pipeline_stream(agent, provider, ctx, user_message, history, spans, usage, out):
                yield ev
        else:
            async for ev in _react_stream(agent, provider, ctx, user_message, history, spans, usage, out):
                yield ev
    except Exception as exc:
        err = Span(type="error", name=type(exc).__name__, detail=str(exc)[:500], status="error")
        err.finish(status="error")
        spans.append(err)
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}

    final_output = out["final"]
    if final_output:
        for piece in _stream_playback(final_output):
            yield {"type": "token", "content": piece}
            await asyncio.sleep(PLAYBACK_DELAY)

    duration_ms = int((time.perf_counter() - started) * 1000)
    db2 = get_session_factory()()
    try:
        if final_output:
            db2.add(Message(
                conversation_id=conversation_id, role="assistant", content=final_output,
                run_id=run_id,
                meta={"tool_calls": sum(1 for s in spans if s.type == "tool")},
            ))
        run = db2.get(Run, run_id) if run_id else None
        if run:
            run.output = final_output
            run.spans = spans.to_list()
            run.usage = usage
            run.status = "succeeded" if final_output else "failed"
            if not final_output:
                run.error = run.error or "执行未产出回答"
            from datetime import datetime, timezone

            run.finished_at = datetime.now(timezone.utc)
            run.duration_ms = duration_ms
        for art_path, art_kind in ctx.artifacts:
            db2.add(Artifact(run_id=run_id, kind=art_kind, path=art_path))
        db2.commit()
    finally:
        db2.close()

    yield {"type": "final", "content": final_output, "usage": usage, "run_id": run_id,
           "duration_ms": duration_ms}
    yield {"type": "done"}


# ---------------------------------------------------------------- ReAct 模式

async def _react_stream(
    agent: Agent,
    provider: BaseProvider,
    ctx: ToolContext,
    user_message: str,
    history: list[dict],
    spans: SpanList,
    usage: dict,
    out: dict,
) -> AsyncIterator[dict]:
    settings = ctx.settings
    rag_block, rag_span = retrieve_context(ctx, agent.dataset_ids or [], user_message)
    spans.append(rag_span)
    if rag_block:
        yield {"type": "retrieval", "hits": rag_span.meta.get("hits", 0) if rag_span.meta else 0, "detail": rag_span.detail}

    system = agent.system_prompt or "你是一个乐于助人的 AI 助手。"
    if agent.tools:
        system += (
            f"\n\n你可以使用以下工具：{', '.join(agent.tools)}。"
            "需要外部信息时必须先调用工具获取，再基于结果回答；不要编造事实。"
        )
    if rag_block:
        system += rag_block

    messages: list[dict] = [{"role": "system", "content": system}, *history,
                            {"role": "user", "content": user_message}]
    schemas = tool_schemas(agent.tools or [])
    max_iters = agent.max_iterations or settings.max_iterations

    for _ in range(max_iters):
        span = spans.new(type="llm", name="llm_call",
                         detail=f"可用工具 {len(schemas)} 个",
                         meta={"tools": [s["function"]["name"] for s in schemas]})
        result = await provider.chat(
            messages, tools=schemas or None,
            model=(agent.llm_config or {}).get("model"),
            temperature=(agent.llm_config or {}).get("temperature"),
            max_tokens=(agent.llm_config or {}).get("max_tokens"),
        )
        merge_usage(usage, result.usage)
        span.finish(
            detail=result.content[:300] if result.content else f"发起 {len(result.tool_calls)} 个工具调用",
            meta={"tool_calls": [tc.name for tc in result.tool_calls],
                  "finish_reason": result.finish_reason},
        )

        if result.tool_calls:
            if result.content:
                yield {"type": "thought", "content": result.content}
            messages.append(_assistant_tool_call_msg(result.content, result.tool_calls))
            for tc in result.tool_calls:
                yield {"type": "tool_call", "tool": tc.name, "args": tc.arguments}
                ok, output, elapsed = await execute_tool(tc.name, tc.arguments, ctx)
                register_chart_artifacts(ctx, output)
                span_t = spans.new(
                    type="tool", name=tc.name,
                    detail=f"参数: {json.dumps(tc.arguments, ensure_ascii=False)[:200]}",
                    meta={"ok": ok, "elapsed_ms": elapsed},
                )
                span_t.finish(detail=output[:300], status="ok" if ok else "error")
                yield {"type": "tool_result", "tool": tc.name, "ok": ok, "elapsed_ms": elapsed,
                       "output": output[:TOOL_RESULT_EVENT_LIMIT]}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": output})
            continue

        out["final"] = result.content or "（模型未返回内容）"
        return

    # 迭代耗尽兜底：不带工具强制做一次总结调用，基于已有工具结果产出回答
    span = spans.new(type="llm", name="llm_final", detail="迭代耗尽，强制总结")
    messages.append({"role": "user",
                     "content": "工具调用次数已达上限。请立即停止调用工具，基于以上已获得的全部工具结果直接给出最终回答。"})
    result = await provider.chat(
        messages, tools=None,
        model=(agent.llm_config or {}).get("model"),
        temperature=(agent.llm_config or {}).get("temperature"),
        max_tokens=(agent.llm_config or {}).get("max_tokens"),
    )
    merge_usage(usage, result.usage)
    span.finish(detail=(result.content or "")[:300])
    out["final"] = result.content or "已达最大迭代次数且未能生成总结，请简化问题后重试。"


# ---------------------------------------------------------------- Pipeline 模式

async def _pipeline_stream(
    agent: Agent,
    provider: BaseProvider,
    ctx: ToolContext,
    user_message: str,
    history: list[dict],
    spans: SpanList,
    usage: dict,
    out: dict,
) -> AsyncIterator[dict]:
    """固定流程编排：每步可用独立工具做 mini-ReAct，产出在步骤间以 {key} 传递。"""
    settings = ctx.settings
    step_outputs: dict[str, str] = {}
    steps = agent.pipeline or []

    for idx, step in enumerate(steps):
        step_name = step.get("name") or f"步骤{idx + 1}"
        step_key = step.get("key") or f"step{idx + 1}"
        yield {"type": "step_started", "index": idx, "name": step_name}
        span = spans.new(type="pipeline_step", name=step_name, detail=f"第 {idx + 1}/{len(steps)} 步")

        variables = {"input": user_message, **step_outputs,
                     "history": json.dumps(history, ensure_ascii=False)}
        prompt = _render(step.get("template", "{input}"), variables)

        system = agent.system_prompt or "你是一个严谨的 AI 助手。"
        system += f"\n\n当前你正在执行工作流「{agent.name}」的第 {idx + 1} 步：{step_name}。请聚焦完成本步任务。"
        if step.get("rag"):
            rag_block, rag_span = retrieve_context(ctx, agent.dataset_ids or [], prompt[:200])
            spans.append(rag_span)
            system += rag_block

        step_tools = step.get("tools") or []
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        schemas = tool_schemas(step_tools)
        max_iters = int(step.get("max_iters", 3))

        output = ""
        for _ in range(max_iters):
            result = await provider.chat(
                messages, tools=schemas or None,
                model=(agent.llm_config or {}).get("model"),
                temperature=(agent.llm_config or {}).get("temperature"),
            )
            merge_usage(usage, result.usage)
            if result.tool_calls:
                if result.content:
                    yield {"type": "thought", "content": result.content}
                messages.append(_assistant_tool_call_msg(result.content, result.tool_calls))
                for tc in result.tool_calls:
                    yield {"type": "tool_call", "tool": tc.name, "args": tc.arguments}
                    ok, out_text, elapsed = await execute_tool(tc.name, tc.arguments, ctx)
                    register_chart_artifacts(ctx, out_text)
                    span_t = spans.new(
                        type="tool", name=tc.name,
                        detail=f"[{step_name}] 参数: {json.dumps(tc.arguments, ensure_ascii=False)[:200]}",
                        meta={"step": step_name, "ok": ok, "elapsed_ms": elapsed},
                    )
                    span_t.finish(detail=out_text[:300], status="ok" if ok else "error")
                    yield {"type": "tool_result", "tool": tc.name, "ok": ok, "elapsed_ms": elapsed,
                           "output": out_text[:TOOL_RESULT_EVENT_LIMIT]}
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": out_text})
                continue
            output = result.content or ""
            break
        else:
            output = "（本步达到迭代上限）"

        step_outputs[step_key] = output
        span.finish(detail=output[:300])
        yield {"type": "step_finished", "index": idx, "name": step_name, "output": output[:800]}
        if step.get("final") or idx == len(steps) - 1:
            out["final"] = output


# ---------------------------------------------------------------- 辅助

def register_chart_artifacts(ctx: ToolContext, tool_output: str) -> None:
    """从工具输出中提取生成的图表路径，登记为本次运行的产物。"""
    for m in re.finditer(r"/files/charts/[\w.-]+", tool_output):
        path = m.group(0)
        if path not in [p for p, _ in ctx.artifacts]:
            ctx.artifacts.append((path, "chart"))


def retrieve_context(
    ctx: ToolContext, dataset_ids: list[str], query: str
) -> tuple[str, Span]:
    """在绑定的文档知识库中检索，返回 (可拼入 system 的资料块, span)。同步快速，无需线程。"""
    span = Span(type="retrieval", name="rag_retrieve", detail=f"query: {query[:120]}")
    if not dataset_ids:
        span.finish("未绑定知识库，跳过检索")
        return "", span

    db = get_session_factory()()
    try:
        doc_ids = [d.id for d in db.query(Dataset).filter(Dataset.id.in_(dataset_ids), Dataset.kind == "docs").all()]
        if not doc_ids:
            span.finish("绑定数据集均非文档类型，跳过检索")
            return "", span
        embedder = get_embedder(ctx.settings)
        qvec = embedder.embed([query])[0]
        hits = vector_store.search(db, doc_ids, qvec, top_k=ctx.settings.rag_top_k)
    finally:
        db.close()

    if not hits:
        span.finish("未检索到相关内容")
        return "", span
    span.meta["hits"] = len(hits)
    lines = ["\n\n【参考资料】以下是知识库中与用户问题相关的片段，回答时请优先依据这些资料并保持准确："]
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}] (相关度 {h['score']}) {h['content'][:400]}")
    span.finish(f"命中 {len(hits)} 条，最高分 {hits[0]['score']}")
    return "\n".join(lines), span
