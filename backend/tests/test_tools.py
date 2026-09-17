"""工具层测试：SQL 只读守卫、Python 沙箱、注册表完整性。"""
import asyncio

import app.tools.handlers  # noqa: F401 触发注册
from app.config import get_settings
from app.tools.registry import ToolContext, execute_tool, list_tools, tool_schemas


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
