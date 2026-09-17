# AgentFlow API 参考

Base URL: `http://localhost:8000`（鉴权开启时请求头带 `X-API-Key`）

统一错误格式：`{"code": 422, "message": "...", "detail": ...}`

## 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/metrics` | 组件状态（LLM/Embedding 模式、各类计数、限流/鉴权开关） |
| GET | `/api/tools` | 内置工具清单（名称/描述/JSON Schema） |
| GET | `/api/artifacts?limit=30` | 图表等产物列表 |

## Agents

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/agents` | 列表 |
| GET | `/api/agents/templates` | 预置模板（客服/销售/研究/数据分析） |
| POST | `/api/agents` | 创建 |
| GET | `/api/agents/{id}` | 详情 |
| PUT | `/api/agents/{id}` | 更新（部分字段） |
| DELETE | `/api/agents/{id}` | 删除 |

Agent 字段：`name, emoji, description, agent_type(react|pipeline), system_prompt, tools[], dataset_ids[], llm_config{}, memory_config{}, pipeline[], max_iterations, enabled`

## 对话

### POST /api/chat

```json
{"agent_id": "...", "message": "你们的退款政策是什么？", "conversation_id": null, "stream": true}
```

- `stream: true` → SSE 事件流，事件类型：
  `run_started` / `retrieval` / `step_started` / `step_finished` / `thought` /
  `tool_call` / `tool_result` / `token` / `final` / `error` / `done`
- `stream: false` → JSON：`{"run_id", "content", "usage", "events": [...]}`

不传 `conversation_id` 时自动创建新会话（从首条消息生成标题）。

## 会话

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/conversations?agent_id=` | 会话列表（按更新时间） |
| GET | `/api/conversations/{id}/messages` | 消息历史 |
| DELETE | `/api/conversations/{id}` | 删除会话 |

## 知识库 / 数据集

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/datasets` | 列表（含文档数） |
| POST | `/api/datasets` | 创建 `{"name", "description", "kind": "docs"|"table"}` |
| GET | `/api/datasets/{id}` | 详情（含文档列表） |
| DELETE | `/api/datasets/{id}` | 删除（级联清理分片） |
| POST | `/api/datasets/{id}/documents` | 上传文件（multipart `file`）。docs: txt/md/csv/pdf → 分块向量化；table: csv/xlsx → 导入 SQLite |
| POST | `/api/datasets/{id}/search` | 检索测试 `{"query", "top_k"}` → 命中片段+相关度 |
| GET | `/api/datasets/{id}/preview` | 表格数据集预览（列 + 前 20 行） |

## 运行记录（Observability）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/runs?limit=50&agent_id=` | 运行列表 |
| GET | `/api/runs/stats` | 总量/成功率/平均耗时/Token 总量 |
| GET | `/api/runs/{id}` | 完整 trace：spans 时间线 + usage + 输入输出 |

## 示例：消费 SSE 流

```python
import httpx, json

with httpx.stream("POST", "http://localhost:8000/api/chat",
                  json={"agent_id": "...", "message": "你好", "stream": True}, timeout=120) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            if ev["type"] == "token":
                print(ev["content"], end="", flush=True)
```
