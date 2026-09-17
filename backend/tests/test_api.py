"""API 集成测试：健康检查、Agent CRUD、知识库、对话链路、运行记录。"""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_agent_crud(client):
    # 创建
    r = client.post("/api/agents", json={"name": "测试Agent", "tools": ["sql_query"]})
    assert r.status_code == 200
    agent = r.json()
    assert agent["name"] == "测试Agent"
    # 修改
    r = client.put(f"/api/agents/{agent['id']}", json={"description": "更新后的描述"})
    assert r.json()["description"] == "更新后的描述"
    # 详情 + 列表
    assert client.get(f"/api/agents/{agent['id']}").status_code == 200
    assert len(client.get("/api/agents").json()["items"]) >= 1
    # 删除
    assert client.delete(f"/api/agents/{agent['id']}").json()["ok"]
    assert client.get(f"/api/agents/{agent['id']}").status_code == 404


def test_seeded_agents_and_datasets(seeded):
    agents = seeded.get("/api/agents").json()["items"]
    names = {a["name"] for a in agents}
    assert {"客服助手", "销售顾问", "行业研究员", "数据分析师"} <= names
    datasets = seeded.get("/api/datasets").json()["items"]
    kinds = {d["kind"] for d in datasets}
    assert "docs" in kinds and "table" in kinds


def test_chat_react_with_rag(seeded):
    """客服 Agent：RAG 检索 -> ReAct 工具调用 -> 最终回答。"""
    agents = seeded.get("/api/agents").json()["items"]
    cs = next(a for a in agents if a["name"] == "客服助手")
    r = seeded.post("/api/chat", json={"agent_id": cs["id"], "message": "退款政策是什么？", "stream": False})
    assert r.status_code == 200
    data = r.json()
    types = [e["type"] for e in data["events"]]
    assert "run_started" in types and "final" in types
    assert "tool_call" in types, "Mock 模型应发起 vector_search 工具调用"
    assert data["content"], "应有最终回答"
    assert data["run_id"]


def test_chat_pipeline(seeded):
    """研究 Agent：三步 pipeline 编排。"""
    agents = seeded.get("/api/agents").json()["items"]
    rs = next(a for a in agents if a["name"] == "行业研究员")
    r = seeded.post("/api/chat", json={"agent_id": rs["id"], "message": "研究AI芯片行业", "stream": False})
    data = r.json()
    steps = [e for e in data["events"] if e["type"] == "step_finished"]
    assert len(steps) == 3, "应顺序完成 3 个工作流步骤"
    assert data["content"]


def test_sse_stream(seeded):
    agents = seeded.get("/api/agents").json()["items"]
    cs = next(a for a in agents if a["name"] == "客服助手")
    with seeded.stream("POST", "/api/chat", json={"agent_id": cs["id"], "message": "你好", "stream": True}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        buf = b""
        for chunk in resp.iter_bytes():
            buf += chunk
            if b'"type": "done"' in buf or b'"type":"done"' in buf:
                break
        text = buf.decode("utf-8")
        assert text.startswith("data:")


def test_runs_recorded(seeded):
    stats = seeded.get("/api/runs/stats").json()
    assert stats["total_runs"] >= 1
    runs = seeded.get("/api/runs").json()["items"]
    assert runs, "至少有一条运行记录"
    detail = seeded.get(f"/api/runs/{runs[0]['id']}").json()
    assert "spans" in detail and detail["spans"]


def test_dataset_search_endpoint(seeded):
    datasets = seeded.get("/api/datasets").json()["items"]
    docs = next(d for d in datasets if d["kind"] == "docs")
    r = seeded.post(f"/api/datasets/{docs['id']}/search", json={"query": "价格", "top_k": 3})
    assert r.status_code == 200
    assert "hits" in r.json()


def test_table_preview(seeded):
    datasets = seeded.get("/api/datasets").json()["items"]
    table = next(d for d in datasets if d["kind"] == "table")
    r = seeded.get(f"/api/datasets/{table['id']}/preview")
    assert r.status_code == 200
    data = r.json()
    assert data["columns"] and len(data["rows"]) > 0


def test_metrics_and_tools(seeded):
    m = seeded.get("/api/metrics").json()
    assert m["llm_provider"] in ("mock", "openai_compatible")
    tools = seeded.get("/api/tools").json()["items"]
    assert len(tools) >= 6
