# AgentFlow 架构设计

## 1. 总体分层

```
Web UI (SPA)
   │  HTTP + SSE
API Gateway（FastAPI 中间件栈）
   │  请求日志 → 限流 → CORS → 鉴权
API Routers（/api/*）
   │
Agent Runtime（执行引擎）
   ├── RAG 子系统（检索增强）
   ├── Tools 注册表（函数调用）
   ├── Memory（会话历史）
   │
LLM Layer（Provider 抽象）
   │
Observability（Trace / Usage / 日志）
   │
SQLite（WAL）
```

依赖方向自上而下，每一层都可以独立替换实现（如 SQLite → PostgreSQL、自研向量存储 → Milvus、Mock → 真实 LLM），因为层与层之间只通过数据结构和协议通信。

## 2. Agent Runtime（核心）

### 2.1 两种运行模式

**ReAct 模式**（`agents/runtime.py: _react_stream`）

```
用户输入
  ↓ 构建 System Prompt（人设 + 工具说明 + RAG 参考资料）
  ↓ 拼接历史窗口记忆
┌─ LLM 调用（携带 OpenAI function calling 的 tools schema）
│    ├─ 返回 tool_calls → 逐个执行工具 → 结果以 role=tool 消息回填 → 回到 LLM
│    └─ 返回纯文本 → 作为最终回答
└─ 最多迭代 max_iterations 轮（防失控）
```

**Pipeline 模式**（`_pipeline_stream`）

```json
[
  {"key": "search",  "name": "检索收集", "tools": ["web_search"], "template": "研究主题：{input} ..."},
  {"key": "verify",  "name": "交叉验证", "tools": ["web_read"],   "template": "... {search} ..."},
  {"key": "report",  "name": "生成报告", "final": true,           "template": "... {verify} ..."}
]
```

- 每步一个 mini-ReAct 循环（独立工具白名单与迭代上限）
- 步骤输出按 `key` 存入变量表，后续步骤用 `{key}` 占位引用（`str.format_map` 安全渲染，未知占位原样保留）
- `final: true` 的步骤输出作为最终回答

### 2.2 事件流协议

Runtime 是异步生成器，产出如下事件，API 层封装为 SSE（`data: {json}\n\n`）：

| 事件 | 载荷 | 用途 |
|---|---|---|
| `run_started` | run_id, conversation_id, agent | 建立会话上下文 |
| `retrieval` | hits, detail | RAG 检索完成提示 |
| `step_started / step_finished` | index, name, output | Pipeline 步骤进度 |
| `thought` | content | 模型工具轮次的中间文本 |
| `tool_call` | tool, args | UI 显示"执行中"气泡 |
| `tool_result` | tool, ok, elapsed_ms, output | 气泡完成态，可展开详情 |
| `token` | content | 最终回答分片（回放式流式） |
| `final` | content, usage, duration_ms | 完整结果 |
| `error` / `done` | - | 结束 |

### 2.3 流式的设计取舍

当前采用**两阶段**：LLM 调用非流式（工具轮与最终轮统一），拿到最终文本后按 24 字符分片回放。
理由：工具轮与回答轮解耦后事件协议最简单，且对前端体验与真实 token 流一致。
升级路径（Roadmap 第 1 项）：provider 增加 `stream=true`，解析 OpenAI 兼容 SSE 的 `delta`，
按 `finish_reason` 区分工具轮/回答轮即可，事件协议无需变动。

## 3. RAG 子系统

```
上传文件 → 文本抽取(txt/md/csv/pdf) → 递归字符分块(500/80，段落→句子→硬切片+重叠窗口)
        → Embedding（本地哈希 or API）→ SQLite BLOB 落库
查询   → 查询向量化 → 内存矩阵点积(归一化后即余弦) → Top-K → 注入 System Prompt【参考资料】块
```

- **本地哈希嵌入**：word token + CJK bigram 经 md5 哈希进 512 维桶，L2 归一化。零依赖离线可用，演示规模下检索排序正确（"退款政策"问题命中对应 FAQ 第 1 位）。
- **向量存储缓存**：per-dataset (matrix, metas) 内存缓存，写入时失效，进程内线程安全。
- **工具化检索**：`vector_search` 同时暴露为 Agent 工具，模型可自主多轮检索（Agentic RAG）。

## 4. 工具系统

注册表模式：`@register(name, description, parameters)` 装饰器登记 `ToolSpec`；
`tool_schemas()` 生成 OpenAI function calling 格式；`execute_tool()` 统一执行、计时、异常捕获
（工具失败不终结运行，错误文本回传给模型自行调整——这是 Agent 工程的重要容错设计）。

| 工具 | 安全措施 |
|---|---|
| `python_exec` | 子进程 + 30s 超时 + 最小环境变量 + cwd 沙箱目录；预置 `DB_PATH` 变量指向平台库；`fig` 变量自动 savefig 并回传 URL |
| `sql_query` | 只读 URI 连接（`mode=ro`）+ 仅允许 SELECT/WITH + 禁止多语句 + 50 行截断 |
| `http_request` / `web_read` | 仅 http(s)、超时、响应截断 |
| `web_search` | DuckDuckGo HTML 解析，失败自动降级 mock 结果（标注来源） |

## 5. Memory

- 短期：会话消息表 + 滑动窗口（默认最近 10 条 user/assistant 消息）注入上下文
- Agent 级可配 `memory_config.window`
- 长期记忆（Roadmap）：历史对话向量化入库，检索注入

## 6. Observability

- **Run 记录**：status / input / output / error / usage / duration
- **Spans**：`llm` / `tool` / `retrieval` / `pipeline_step` / `error` 五类，含起止毫秒、详情、元数据；前端时间线可视化
- **网关日志**：每请求结构化 JSON（method/path/status/耗时/client）
- **指标接口**：`/api/runs/stats`（成功率/平均耗时/Token 总量）、`/api/metrics`（组件状态）
- 升级路径：OpenTelemetry exporter、LLM 调用细粒度 token 计量

## 7. 网关

中间件栈（外→内）：CORS → RequestLog → RateLimit（每 IP 滑动窗口，`deque` 实现，
多实例换 Redis）→ 路由；可选 `X-API-Key` 鉴权（`AGENTFLOW_AUTH_ENABLED=true` 启用）。

## 8. 数据模型（SQLite, WAL）

`agents` / `conversations` / `messages` / `runs` / `datasets` / `documents` / `chunks`（含 embedding BLOB）/ `artifacts` / `crm_customers`

WAL 模式解决演示中"读写并发 + pandas to_sql 二次连接"造成的 `database is locked`。

## 9. 安全边界（如实声明）

`python_exec` 为**演示级隔离**：子进程 + 超时 + 最小 env，但未做容器/系统调用级隔离，不应直接暴露给不可信用户。
生产方案：每工具调用一个 gVisor/Firecracker 微 VM 或独立容器池，配网络策略。
`sql_query` 通过 SQLite 只读连接兜底，即使守卫正则被绕过也无法写库。
