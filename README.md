# AgentFlow —— 企业级 AI Agent 工作平台

> 一个简化版的 **Dify + Coze + n8n + AI Agent**：可视化创建 Agent、绑定工具与知识库、ReAct 自主推理 / Pipeline 工作流编排、RAG 检索增强、可观测性 Trace，开箱即用。

![Python](https://img.shields.io/badge/Python-3.11+-3776ab) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688) ![Tests](https://img.shields.io/badge/tests-29%20passed-3fb950) ![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ 核心能力

| 能力 | 说明 |
|---|---|
| **Agent 工作台** | 创建/编辑 Agent：自定义人设提示词、工具组合、知识库绑定、迭代上限 |
| **双运行时** | `ReAct`（LLM + 原生 Function Calling 自主循环调用工具）/ `Pipeline`（固定步骤工作流，步骤间变量传递，类 n8n） |
| **RAG 知识库** | 上传 txt/md/pdf → 递归分块 → 向量化（本地哈希嵌入或 OpenAI 兼容 Embedding API）→ 余弦相似度 Top-K 检索，检索结果自动注入 System Prompt |
| **7 个内置工具** | `web_search`（DuckDuckGo）/ `web_read` / `http_request` / `python_exec`（沙箱+图表自动保存）/ `sql_query`（只读守卫）/ `crm_lookup` / `vector_search` |
| **数据分析 Agent** | 上传 Excel/CSV → 自动导入 SQLite → Agent 生成 SQL/Python → 沙箱执行 → matplotlib 图表自动保存 → 在线查看 |
| **可观测性** | 每次运行完整 Trace：LLM 调用 / 工具执行 / RAG 检索的 span 时间线、Token 用量、耗时，UI 可视化查看 |
| **网关** | 请求日志（结构化 JSON）、滑动窗口限流、可选 API Key 鉴权、CORS（默认只放行本地前端） |
| **流式体验** | SSE 事件流：`thought` / `tool_call` / `tool_result` / `token` / `artifact` 实时推送 |
| **零依赖演示** | 内置 Mock LLM + 本地哈希 Embedding：**无需任何 API Key 即可跑通全部链路** |

## 🏗️ 架构

```
                        ┌───────────────────┐
                        │      Web UI       │  原生 JS SPA（免构建）
                        └─────────┬─────────┘
                                  ↓ HTTP / SSE
                     ┌────────────────────────┐
                     │      API Gateway       │  FastAPI + 日志/限流/鉴权/CORS
                     └────────────┬───────────┘
                                  ↓
                     ┌────────────────────────┐
                     │     Agent Runtime      │  ReAct 循环 · Pipeline 编排 · 事件流
                     └──┬─────────┬────────┬──┘
                        ↓         ↓        ↓
                  ┌──────────┐ ┌──────────┐ ┌──────────┐
                  │   RAG    │ │  Tools   │ │  Memory  │
                  │ 分块/嵌入 │ │ 搜索/代码 │ │ 会话窗口  │
                  │ 向量检索  │ │ SQL/CRM  │ │ 历史加载  │
                  └────┬─────┘ └────┬─────┘ └────┬─────┘
                       └────────────┼────────────┘
                                    ↓
                     ┌────────────────────────┐
                     │   LLM Layer            │  OpenAI 兼容接口 / Mock（离线）
                     └────────────┬───────────┘
                                  ↓
                     ┌────────────────────────┐
                     │     Observability      │  Spans Trace + Usage + JSON 日志
                     └────────────────────────┘
                            SQLite（WAL）：agents / messages / runs / chunks / datasets ...
```

详细设计见 [docs/architecture.md](docs/architecture.md)，接口清单见 [docs/api.md](docs/api.md)。

## 🚀 快速开始

```bash
# 1. 安装依赖（建议 Python 3.11+）
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows；macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. 初始化演示数据（知识库 FAQ / CRM 客户 / 4 个预置 Agent / 销售样例表）
python -m scripts.seed_demo

# 3. 启动
python -m app.main                # 或 uvicorn app.main:app --reload --port 8000
```

打开 **http://localhost:8000** 即可使用。

> 端口被占用时：`uvicorn app.main:app --port 8001`，或在 `backend/.env` 中配置 `AGENTFLOW_PORT`。

### 接入真实大模型（可选）

复制根目录 `.env.example` 为 `backend/.env`，填入任意 OpenAI 兼容接口：

```ini
AGENTFLOW_LLM_PROVIDER=openai_compatible
AGENTFLOW_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4   # 智谱；DeepSeek: https://api.deepseek.com/v1
AGENTFLOW_LLM_API_KEY=你的Key
AGENTFLOW_LLM_MODEL=glm-4-flash
```

不配置时自动使用内置 Mock 模型（关键词脚本化：会真实调用工具链，回答为模拟文本），项目依然完整可演示。

## 🎬 四个演示场景（面试可现场 Demo）

| Agent | 输入示例 | 背后链路 |
|---|---|---|
| 🎧 客服助手 | `你们的退款政策是什么？` | RAG 检索知识库 → ReAct 调用 vector_search → 引用资料回答 |
| 💼 销售顾问 | `帮我分析一下客户 王强` | crm_lookup 查档案 → 客户画像 → 生成跟进方案 |
| 🔬 行业研究员 | `帮我研究新能源汽车行业` | Pipeline 三步：检索收集(web_search) → 阅读交叉验证(web_read) → 生成报告 |
| 📊 数据分析师 | `各地区的销售额分布如何？画个图` | sql_query 摸表 → python_exec(pandas+matplotlib) → 图表自动保存 → 报告 |

## 📁 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # 应用装配：网关中间件 / 路由 / 静态资源
│   │   ├── config.py            # 环境变量配置（AGENTFLOW_ 前缀）
│   │   ├── api/                 # 路由层：agents / chat(SSE) / datasets / runs / system
│   │   ├── agents/
│   │   │   ├── runtime.py       # ★ Agent 执行引擎（ReAct + Pipeline + 事件流）
│   │   │   └── templates.py     # 4 个预置 Agent 模板
│   │   ├── llm/
│   │   │   ├── provider.py      # OpenAI 兼容 Provider + Mock Provider
│   │   │   └── embeddings.py    # 本地哈希嵌入 / Embedding API
│   │   ├── rag/                 # chunker / vector store / 入库管道
│   │   ├── tools/               # 工具注册表 + 7 个内置工具实现
│   │   ├── memory/              # 会话历史窗口
│   │   ├── observability/       # Span 追踪
│   │   ├── core/                # 网关中间件 / 统一错误处理
│   │   └── db/                  # SQLAlchemy 模型与会话
│   ├── scripts/seed_demo.py     # 演示数据种子
│   └── tests/                   # 26 个 pytest 用例
├── frontend/                    # 免构建原生 JS SPA（6 个页面）
├── docs/                        # 架构文档 / API 文档
├── Dockerfile / docker-compose.yml
└── .env.example
```

## 🧪 测试

```bash
cd backend
python -m pytest tests/ -q          # 26 passed
```

覆盖：分块器、RAG 入库与检索、SQL 只读守卫、Python 沙箱（含 DB_PATH 注入与报错捕获）、
ReAct 对话全链路、Pipeline 三步编排、SSE 流式、运行记录落库、Agent CRUD。

## 🐳 Docker 部署

```bash
docker compose up --build
# 访问 http://localhost:8000，数据持久化在 ./data 卷
```

## 💡 面试 talking points（设计取舍）

- **为什么两阶段流式（非流式 LLM 调用 + 回放式 token 推送）？** 工具轮次与最终回答解耦，事件协议简单可靠；升级路径：provider 层加 `stream=true` 透传 SSE delta，前端协议不变。
- **为什么自研向量存储而不是 Chroma/Milvus？** 演示规模（万级分片）下 SQLite BLOB + numpy 余弦足够，接口与专业向量库一致可平滑替换；重点展示对检索原理的理解而非堆组件。
- **Python 沙箱的安全边界？** 子进程 `-I` 隔离 + 工具级/进程级超时 + 最小环境变量 + 运行时屏蔽 `socket`；生产应换容器级隔离（gVisor/firecracker）。注意：这不是强安全边界——注入的 `DB_PATH`、文件系统与导入机制仍可被利用，属演示级隔离，简历上要能说清边界。
- **SSRF / 上传安全？** `web_read` / `http_request` 只允许公网 http(s) 地址，拒绝解析到内网/本机/云元数据地址的主机；`web_read` 手动跟随重定向并逐跳复检，`http_request` 不自动跟随重定向；上传只保留文件名 basename，并把最终路径限制在 uploads 目录内。
- **对外部署要注意什么？** 默认只监听 `127.0.0.1` 且关闭鉴权；对外部署请设置 `AGENTFLOW_AUTH_ENABLED=true` 与强 `AGENTFLOW_API_KEY`，收紧 `AGENTFLOW_CORS_ORIGINS`，并在反向代理层加 TLS/限流。
- **Mock Provider 的价值？** 演示环境零依赖、CI 可测试、面试可复现；脚本化工具调用保证了 ReAct 循环的确定性测试。
- **限流为什么先用内存版？** 单进程滑动窗口够用；多实例部署换 Redis `INCR+EXPIRE`，中间件接口不变。

## 🗺️ Roadmap

- [ ] LLM 直连 token 级流式（provider stream=true）
- [ ] 可视化 Pipeline 编辑器（拖拽 DAG）
- [ ] Redis Memory + 长期记忆（向量检索历史对话）
- [ ] 多租户与 RBAC
- [ ] OpenTelemetry 导出
- [ ] MCP 工具协议接入
