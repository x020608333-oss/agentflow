"""内置工具实现。"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import sys
import uuid

import httpx
from bs4 import BeautifulSoup

from app.db.models import CrmCustomer
from app.llm.embeddings import get_embedder
from app.rag.store import vector_store
from app.tools.registry import ToolContext, register

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentFlow/0.1"


def _mock_search_results(query: str) -> list[dict]:
    base = [
        {"title": f"{query} —— 行业研究报告（模拟）", "url": "https://example.com/report", "snippet": f"关于「{query}」的市场规模、竞争格局与发展趋势综述。"},
        {"title": f"{query} 最新动态", "url": "https://example.com/news", "snippet": f"「{query}」相关的最新资讯与政策解读（模拟数据）。"},
        {"title": f"{query} 百科", "url": "https://example.com/wiki", "snippet": f"「{query}」的定义、产业链上下游与关键参与方介绍（模拟数据）。"},
    ]
    return base


@register(
    "web_search",
    "联网搜索。输入搜索关键词 query，返回网页标题、链接与摘要列表。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "返回条数，默认 5"},
        },
        "required": ["query"],
    },
)
async def web_search(args: dict, ctx: ToolContext) -> str:
    query = str(args.get("query", "")).strip()
    max_results = int(args.get("max_results", 5))
    if not query:
        return "错误: query 不能为空"

    if not ctx.settings.net_tools_enabled:
        return json.dumps({"query": query, "results": _mock_search_results(query), "source": "mock"}, ensure_ascii=False)

    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": UA}, follow_redirects=True) as client:
            resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for a in soup.select("a.result__a")[: max_results * 2]:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or not href:
                continue
            if href.startswith("//duckduckgo.com/l/?uddg="):
                m = re.search(r"uddg=([^&]+)", href)
                if m:
                    from urllib.parse import unquote

                    href = unquote(m.group(1))
            snippet_el = a.find_parent(class_="result")
            snippet = snippet_el.select_one(".result__snippet") if snippet_el else None
            results.append({"title": title, "url": href, "snippet": snippet.get_text(strip=True) if snippet else ""})
            if len(results) >= max_results:
                break
        if not results:
            results = _mock_search_results(query)
            return json.dumps({"query": query, "results": results, "source": "mock(无真实结果)"}, ensure_ascii=False)
        return json.dumps({"query": query, "results": results, "source": "duckduckgo"}, ensure_ascii=False)
    except Exception as exc:
        results = _mock_search_results(query)
        return json.dumps(
            {"query": query, "results": results, "source": f"mock(搜索失败: {type(exc).__name__})"},
            ensure_ascii=False,
        )


@register(
    "web_read",
    "读取指定 URL 网页的正文文本内容。用于在搜索后深入了解某个网页。",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "网页地址，必须以 http(s):// 开头"}},
        "required": ["url"],
    },
)
async def web_read(args: dict, ctx: ToolContext) -> str:
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "错误: url 必须以 http(s):// 开头"
    if not ctx.settings.net_tools_enabled:
        return f"[模拟网页内容] 这是 {url} 的正文摘要（离线模式返回模拟文本）：页面介绍了与该主题相关的背景、数据与结论。"
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+\n", "\n", soup.get_text("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:6000] if text else "（页面无可提取正文）"


@register(
    "http_request",
    "调用 HTTP API。可指定 method/url/headers/body，返回状态码与响应内容（截断至 3000 字符）。",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "description": "默认 GET"},
            "headers": {"type": "object", "description": "请求头"},
            "body": {"type": "object", "description": "JSON 请求体"},
        },
        "required": ["url"],
    },
)
async def http_request(args: dict, ctx: ToolContext) -> str:
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return "错误: url 必须以 http(s):// 开头"
    method = str(args.get("method", "GET")).upper()
    headers = {str(k): str(v) for k, v in (args.get("headers") or {}).items()}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.request(method, url, headers=headers, json=args.get("body"))
    return f"HTTP {resp.status_code}\n{resp.text[:3000]}"


@register(
    "python_exec",
    "在受限沙箱中执行 Python 代码（无网络），返回 stdout/stderr。"
    "分析数据请用 pandas，画图请用 matplotlib 并把 Figure 赋值给变量 fig，图表会自动保存并返回访问链接。",
    {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "完整 Python 代码"}},
        "required": ["code"],
    },
)
async def python_exec(args: dict, ctx: ToolContext) -> str:
    code = str(args.get("code", "")).strip()
    if not code:
        return "错误: code 不能为空"
    if len(code) > 20000:
        return "错误: 代码过长（>20000 字符）"

    settings = ctx.settings
    settings.sandbox_dir.mkdir(parents=True, exist_ok=True)
    chart_name = f"chart_{uuid.uuid4().hex[:10]}.png"
    chart_path = settings.charts_dir / chart_name

    # 包装用户代码：预置 DB_PATH 指向平台数据库；配置中文字体；捕获 fig 变量自动保存图表。
    # 完成标记只回传纯 ASCII 文件名，避免中文路径在不同控制台代码页下的编码不一致问题。
    wrapper = (
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'PingFang SC', 'sans-serif']\n"
        "matplotlib.rcParams['axes.unicode_minus'] = False\n"
        f"_g = {{'DB_PATH': r'{settings.db_path}'}}\n"
        f"exec(compile({code!r}, 'user_code', 'exec'), _g)\n"
        f"if 'fig' in _g:\n"
        f"    _g['fig'].savefig(r'{chart_path}', dpi=120, bbox_inches='tight')\n"
        f"    print('CHART_SAVED::{chart_name}')\n"
    )
    wrapper_file = settings.sandbox_dir / f"exec_{uuid.uuid4().hex[:10]}.py"
    wrapper_file.write_text(wrapper, encoding="utf-8")

    try:
        import os

        mpl_cache = settings.sandbox_dir / ".mplcache"
        mpl_cache.mkdir(exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(wrapper_file),
            cwd=str(settings.sandbox_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={
                "MPLBACKEND": "Agg",
                "MPLCONFIGDIR": str(mpl_cache),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "PYTHONIOENCODING": "utf-8",
            },
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            return "错误: 代码执行超时（>30s），已终止"
        output = out.decode("utf-8", errors="replace").strip()
    finally:
        wrapper_file.unlink(missing_ok=True)

    chart_url = None
    if f"CHART_SAVED::{chart_name}" in output:
        chart_url = f"/files/charts/{chart_name}"
        output = output.replace(f"CHART_SAVED::{chart_name}", "").strip()
    if chart_url:
        return f"{output}\n\n[图表已生成] {chart_url}"
    return output or "（代码执行完成，无输出）"


def _connect_readonly(settings) -> sqlite3.Connection:
    uri = f"file:{settings.db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


@register(
    "sql_query",
    "对平台 SQLite 数据库执行只读 SQL 查询（仅允许 SELECT）。"
    "业务表：crm_customers(客户)；知识库表格数据集为 tbl_xxxxxx（可用 SELECT name FROM sqlite_master WHERE type='table' 查看所有表）。",
    {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "只读 SELECT 语句"}},
        "required": ["sql"],
    },
)
async def sql_query(args: dict, ctx: ToolContext) -> str:
    sql = str(args.get("sql", "")).strip().rstrip(";")
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        return "错误: 仅允许 SELECT/WITH 只读查询"
    if ";" in sql:
        return "错误: 不允许多条语句"
    conn = _connect_readonly(ctx.settings)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(50)
        cols = [d[0] for d in cur.description] if cur.description else []
    finally:
        conn.close()
    if not cols:
        return "查询成功：无结果集"
    table = "| " + " | ".join(cols) + " |\n"
    table += "| " + " | ".join(["---"] * len(cols)) + " |\n"
    for row in rows:
        table += "| " + " | ".join("" if v is None else str(v) for v in row) + " |\n"
    return f"查询成功，返回 {len(rows)} 行（最多显示 50 行）：\n{table}"


@register(
    "crm_lookup",
    "查询 CRM 客户信息。支持按姓名/公司/电话关键词模糊搜索，返回客户阶段、商机金额、行业等。",
    {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "客户姓名、公司名或电话关键词"}},
        "required": ["keyword"],
    },
)
async def crm_lookup(args: dict, ctx: ToolContext) -> str:
    keyword = str(args.get("keyword", "")).strip()
    from sqlalchemy import or_

    from app.db.session import get_session_factory

    db = get_session_factory()()
    try:
        q = db.query(CrmCustomer)
        if keyword:
            like = f"%{keyword}%"
            q = q.filter(
                or_(
                    CrmCustomer.name.like(like),
                    CrmCustomer.company.like(like),
                    CrmCustomer.phone.like(like),
                    CrmCustomer.industry.like(like),
                )
            )
        rows = q.limit(10).all()
        if not rows:
            return f"未找到与「{keyword}」相关的客户"
        data = [
            {
                "name": r.name, "company": r.company, "phone": r.phone,
                "stage": r.stage, "deal_size": r.deal_size, "industry": r.industry,
                "last_contact": r.last_contact, "notes": r.notes,
            }
            for r in rows
        ]
        return json.dumps({"count": len(data), "customers": data}, ensure_ascii=False)
    finally:
        db.close()


@register(
    "vector_search",
    "在知识库（文档向量库）中语义检索相关片段。query 为检索问题；未指定 dataset_id 时检索该 Agent 绑定的全部知识库。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题"},
            "dataset_id": {"type": "string", "description": "可选，指定知识库 ID"},
            "top_k": {"type": "integer", "description": "返回条数，默认 4"},
        },
        "required": ["query"],
    },
)
async def vector_search(args: dict, ctx: ToolContext) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "错误: query 不能为空"
    top_k = int(args.get("top_k", 4))
    dataset_id = args.get("dataset_id")
    dataset_ids = [dataset_id] if dataset_id else ctx.default_dataset_ids
    if not dataset_ids:
        return "该 Agent 未绑定任何知识库，无法检索"

    from app.db.session import get_session_factory

    db = get_session_factory()()
    try:
        embedder = get_embedder(ctx.settings)
        qvec = embedder.embed([query])[0]
        hits = vector_store.search(db, dataset_ids, qvec, top_k=top_k)
    finally:
        db.close()
    if not hits:
        return "知识库中未检索到相关内容"
    return json.dumps(
        {"hits": [{"score": h["score"], "content": h["content"][:500]} for h in hits]},
        ensure_ascii=False,
    )


@register(
    "current_time",
    "获取当前日期时间（本地时区）。回答时间相关问题前可调用。",
    {"type": "object", "properties": {}},
)
async def current_time(args: dict, ctx: ToolContext) -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
