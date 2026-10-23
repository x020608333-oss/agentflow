"""工具层测试：SQL 只读守卫、Python 沙箱、注册表完整性。"""
import asyncio

import app.tools.handlers  # noqa: F401 触发注册
from app.api.routes.datasets import _safe_upload_path
from app.config import get_settings
from app.tools.registry import (
    REGISTRY,
    ToolContext,
    ToolSpec,
    execute_tool,
    list_tools,
    tool_schemas,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_registry_has_core_tools():
    names = {t.name for t in list_tools()}
    assert {"web_search", "web_read", "python_exec", "sql_query", "crm_lookup", "vector_search"} <= names


def test_tool_schemas_format():
    schemas = tool_schemas(["sql_query", "不存在"])
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "sql_query"


def test_sql_guard_blocks_write():
    ctx = ToolContext(settings=get_settings())
    _ok, out, _ = _run(execute_tool("sql_query", {"sql": "DROP TABLE agents"}, ctx))
    assert "仅允许" in out  # 守卫拦截并返回说明，不会执行写操作


def test_sql_guard_blocks_multi_statement():
    ctx = ToolContext(settings=get_settings())
    _ok, out, _ = _run(execute_tool("sql_query", {"sql": "SELECT 1; DROP TABLE agents"}, ctx))
    assert "不允许多条语句" in out


def test_sql_readonly_select_works():
    ctx = ToolContext(settings=get_settings())
    ok, out, _ = _run(execute_tool("sql_query", {"sql": "SELECT COUNT(*) AS n FROM crm_customers"}, ctx))
    assert ok
    assert "查询成功" in out


def test_python_exec_basic():
    ctx = ToolContext(settings=get_settings())
    ok, out, _ = _run(execute_tool("python_exec", {"code": "print(1+1)"}, ctx))
    assert ok
    assert "2" in out


def test_python_exec_exposes_db_path():
    ctx = ToolContext(settings=get_settings())
    code = "import sqlite3, os\ncon = sqlite3.connect(DB_PATH)\nprint(con.execute('SELECT COUNT(*) FROM agents').fetchone()[0])"
    ok, out, _ = _run(execute_tool("python_exec", {"code": code}, ctx))
    assert ok
    assert out.strip().isdigit(), out


def test_python_exec_error_captured():
    ctx = ToolContext(settings=get_settings())
    ok, out, _ = _run(execute_tool("python_exec", {"code": "1/0"}, ctx))
    assert ok  # 执行本身成功，错误在输出中
    assert "ZeroDivisionError" in out


def test_unknown_tool():
    ctx = ToolContext(settings=get_settings())
    ok, out, _ = _run(execute_tool("不存在的工具", {}, ctx))
    assert not ok


def test_web_tools_block_private_and_metadata_urls():
    ctx = ToolContext(settings=get_settings())
    for url in ("http://127.0.0.1:8000/api/health", "http://localhost:8000/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/"):
        for tool in ("web_read", "http_request"):
            ok, out, _ = _run(execute_tool(tool, {"url": url}, ctx))
            assert "内网" in out or "本机" in out or "保留" in out, (tool, url, out)


def test_upload_filename_traversal_is_sanitized():
    path, name = _safe_upload_path("ds12345678", "../../evil.txt")
    assert name == "evil.txt"
    assert path.parent == get_settings().uploads_dir.resolve()
    assert ".." not in path.name


def test_tool_timeout_is_enforced():
    async def slow(args, ctx):
        await asyncio.sleep(1)
        return "done"

    REGISTRY["_slow_test"] = ToolSpec("_slow_test", "test", {}, slow)
    ctx = ToolContext(settings=get_settings())
    original = ctx.settings.tool_timeout
    try:
        ctx.settings.tool_timeout = 0.05
        ok, out, _ = _run(execute_tool("_slow_test", {}, ctx))
        assert not ok
        assert "超时" in out
    finally:
        ctx.settings.tool_timeout = original
        REGISTRY.pop("_slow_test", None)
