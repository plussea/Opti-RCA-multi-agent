# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

OmniOps — 结构化数据驱动的智能诊断与建议系统。运维团队通过上传 CSV/OCR 表格数据，由 MultiAgent 协作完成根因定位与修复建议生成，工程师人工审核后执行。

**核心架构**：事件驱动状态机 + RabbitMQ 解耦各 Agent，支持水平扩展。

## 开发环境

```bash
# 安装依赖（使用 uv）
uv sync
uv sync --extra dev

# 运行测试
uv run pytest tests/ -v          # 129 passed, 2 skipped（包含 PostgreSQL 集成测试）
uv run pytest tests/unit/ -v     # 单元测试
uv run pytest tests/integration/test_db_store.py -v  # PostgreSQL 持久化测试

# 代码检查
uv run ruff check src/ tests/
uv run mypy src/

# Demo（无需外部服务）
uv run python demo.py

# 启动服务
uv run python -m omniops.api.main

# Docker 环境（完整，含前端）
docker compose up --build -d
# 访问 http://localhost/        → 前端（nginx → nextjs）
# 访问 http://localhost/v1/health → 后端健康检查
# 访问 http://localhost:15672    → RabbitMQ 管理界面
```

## 技术栈

- **语言**: Python 3.8+（注意：typing 需用 `List/Dict/Optional` 而非内置泛型 `list[]/dict[]`）
- **API 框架**: FastAPI + Uvicorn
- **消息队列**: RabbitMQ（`aio-pika` 异步客户端）
- **Agent 通信**: RabbitMQ topic exchange + 状态机事件驱动
- **存储**: Redis（会话缓存）+ PostgreSQL（持久化）+ SQLite向量库（RAG）
- **图数据库**: Neo4j（拓扑关系，已接入）
- **LLM**: Model Registry 模式，支持 Anthropic / OpenAI / OpenRouter / MiniMax
- **配置管理**: Pydantic Settings（`SettingsConfigDict`）
- **依赖管理**: uv + pyproject.toml
- **测试**: pytest + pytest-asyncio

## 项目结构

```
src/omniops/
├── agents/              # Agent 实现
│   ├── base.py         # BaseAgent 抽象基类
│   ├── perception.py   # 感知 Agent：CSV 解析、表头标准化
│   ├── diagnosis.py     # 诊断 Agent：规则推理 + LLM 根因分析
│   ├── impact.py       # 影响 Agent：影响范围评估
│   ├── planning.py      # 方案 Agent：修复建议生成（LLM + 模板）
│   └── verification.py  # 校验 Agent：方案自洽性验证
├── api/
│   ├── main.py         # FastAPI 入口 + lifespan（MQ 消费者生命周期）
│   └── routes.py       # REST API 路由
├── consumers/           # RabbitMQ 消费者（每个 Agent 一个）
│   ├── diagnosis_consumer.py
│   ├── impact_consumer.py
│   ├── planning_consumer.py
│   ├── verification_consumer.py
│   ├── human_review_consumer.py   # 人工审核 + 超时 DLQ
│   └── closure_consumer.py        # 知识闭环写入向量库
├── core/
│   ├── config.py       # Settings 单例（含 MQ/HITL 配置）
│   ├── encoding.py     # CSV 编码检测
│   ├── topology_manager.py  # 光网络拓扑图查询（邻居/链路/影响范围）
│   └── providers/      # LLM Model Registry
│       ├── base.py     # ProviderConfig + BaseProvider ABC
│       ├── openai_provider.py
│       ├── openrouter_provider.py
│       └── minimax_provider.py
├── events/            # 事件总线
│   ├── schemas.py     # 所有事件 Pydantic 模型
│   └── publisher.py   # RabbitMQ 发布器（降级为 stub log）
├── ingestion/
│   └── csv_parser.py  # CSV 摄取 + 表头标准化 + 拓扑 id/定位信息解析
├── memory/
│   ├── store.py       # 内存会话存储
│   ├── redis_store.py # Redis 异步会话存储（含原子状态更新）
│   └── db_store.py    # PostgreSQL 持久化存储
├── models/
│   ├── session.py     # Session + SessionStatus（状态机枚举）
│   └── knowledge.py   # CognitiveSummary 协议
├── mq/                # RabbitMQ 基础设施
│   ├── connection.py   # aio-pika 连接管理
│   ├── setup.py       # exchanges/queues/DLQ 声明
│   └── consumer_base.py  # BaseConsumer 基类
├── rag/
│   └── vector_store.py  # SQLite 向量存储 + RAG 检索
├── knowledge/           # 知识图谱构建与查询
│   ├── neo4j_client.py  # Neo4j 图数据库异步客户端
│   ├── graph_builder.py # 知识图谱构建器（解析文档→Neo4j）
│   ├── entity_parser.py # 实体/关系解析器
│   └── kg_query.py      # 图谱查询服务（子图/路径/社区）
└── router/
    └── context_router.py  # 状态机调度器（route_after_agent）
```

## 关键模式

### 事件驱动状态机

Session 通过 `current_step` 字段追踪流水线位置，状态流转：

```
init → perceived → diagnosing → planning → verifying → pending_human → resolving → resolved
                                                    ↓
                                              (needs_approval=false → completed)
```

- `ContextRouter.route_after_agent(session, agent_name)` 每次 Agent 完成后调用，决定下一步
- `ContextRouter.decide_next_agent_after_completion(session)` 消费 completed 事件后调用
- 事件发布到 RabbitMQ，各 Agent 消费者独立扩缩容（保底路径）
- **同步链路优先**：上传 CSV 后，`_run_agent_chain_sync()` 同步执行感知→诊断→影响→方案→校验，响应快；RabbitMQ 消费者作为保底，幂等处理重复事件（不重复处理已在同步链路完成的 session）

### 新增 Provider（Model Registry）

```python
from omniops.core.providers import get_provider

# 默认从 LLM_PROVIDER 环境变量读取
provider = get_provider()
result = await provider.generate_json(system="...", user_message="...")

# 显式指定
provider = get_provider("openrouter")
```

通过 `@register("name")` 装饰器扩展新 Provider，只需新建文件无需改其他代码。

### 会话存储（双写模式）

消费者同时写入 Redis（实时）和 PostgreSQL（持久化），任一层失败不影响链路：

```python
# 每个 consumer 内的 _persist() 调用序列
await redis_store.update(session_id, status=..., diagnosis_result=...)
await db_store.create(session)         # 幂等：DELETE 后 INSERT
await db_store.save_conversation(...)  # Agent 对话记录
```

`DBSessionStore.create()` 为幂等实现，允许重复运行测试和数据隔离。

### Agent 开发

- 继承 `BaseAgent`，实现 `async process(session, context) -> CognitiveSummary`
- Consumer 负责：从 Redis 加载 session → 调用 Agent → 写回 Redis → 发布下一事件
- 返回 `CognitiveSummary` 携带 `required_action` 供 Router 参考

### 数据模型（Python 3.8）

- 用 `Optional[X]` 而非 `X | None`
- 用 `List[X]` 而非 `list[X]`
- 用 `Dict[K, V]` 而非 `dict[K, V]`
- datetime 字段存 ISO 字符串，解析用 `dateutil.parser.parse`

### 消息队列拓扑

| 队列 | 消费者 | 用途 |
|------|--------|------|
| `omniops.diagnosis` | DiagnosisConsumer | 诊断任务 |
| `omniops.impact` | ImpactConsumer | 影响评估 |
| `omniops.planning` | PlanningConsumer | 方案生成 |
| `omniops.verification` | VerificationConsumer | 方案校验 |
| `omniops.human_review` | HumanReviewConsumer | 人工审核 + 超时 DLQ |
| `omniops.closure` | ClosureConsumer | 知识闭环 |

## Docker 服务

| 端口 | 服务 | 说明 |
|------|------|------|
| 80 | Nginx | 反向代理（`/` → nextjs, `/v1/` → omniops） |
| 5432 | PostgreSQL | 持久存储（含 pgvector 向量） |
| 6379 | Redis | 会话缓存 |
| 5672 | RabbitMQ AMQP | 消息队列 |
| 8000 | OmniOps API | 主服务（nginx 后） |
| 15672 | RabbitMQ UI | 管理界面 |
| 7474/7687 | Neo4j | 图数据库 |
| 3000 | Next.js Frontend | 前端（nginx 后） |

## 环境变量（关键）

```bash
LLM_PROVIDER=openrouter        # anthropic | openai | openrouter | minimax
RABBITMQ_URL=amqp://omniops:omniops123@localhost:5672/
HITL_TIMEOUT_SECONDS=600
HITL_ESCALATION_WEBHOOK_URL=   # 企业微信等升级通知
```
