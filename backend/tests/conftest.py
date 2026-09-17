"""测试全局夹具：在导入 app 前把数据目录指向临时目录，锁定离线模式保证确定性、零成本。"""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="agentflow_test_")
os.environ["AGENTFLOW_DATA_DIR"] = _TMP
os.environ["AGENTFLOW_NET_TOOLS_ENABLED"] = "false"
# 测试一律使用 Mock LLM + 本地向量（环境变量优先级高于 backend/.env）
os.environ["AGENTFLOW_LLM_PROVIDER"] = "mock"
os.environ["AGENTFLOW_EMBEDDING_PROVIDER"] = "local"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def seeded(client):
    """复用 seed 脚本准备演示数据（知识库/CRM/4 个 Agent）。"""
    from scripts.seed_demo import seed

    seed(force=False)
    return client
