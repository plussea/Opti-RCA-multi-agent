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
uv run pytest tests/ -v
uv run pytest tests/unit/test_state_machine.py -v   # 状态机测试
uv run pytest tests/unit/test_providers.py -v        # LLM provider 测试

# 代码检查
uv run ruff check src/ tests/
uv run mypy src/

# Demo（无需外部服务）
uv run python demo.py

# 启动服务
uv run python -m omniops.api.main

# Docker 环境（完整）
docker compose up
# 访问 http://localhost:15672 查看 RabbitMQ 管理界面
```

## 技术栈

- **语言**: Python 3.8+（注意：typing 需用 `List/Dict/Optional` 而非内置泛型 `list[]/dict[]`）
- **API 框架**: FastAPI + Uvicorn
- **消息队列**: RabbitMQ（`aio-pika` 异步客户端）
- **Agent 通信**: RabbitMQ topic exchange + 状态机事件驱动
- **存储**: Redis（会话缓存）+ PostgreSQL（持久化）+ SQLite向量库（RAG）
- **图数据库**: Neo4j（拓扑关系，待接入）
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
│   └── providers/      # LLM Model Registry
│       ├── base.py     # ProviderConfig + BaseProvider ABC
│       ├── openai_provider.py
│       ├── openrouter_provider.py
│       └── minimax_provider.py
├── events/            # 事件总线
│   ├── schemas.py     # 所有事件 Pydantic 模型
│   └── publisher.py   # RabbitMQ 发布器（降级为 stub log）
├── ingestion/
│   └── csv_parser.py  # CSV 摄取 + 表头标准化
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
- 事件发布到 RabbitMQ，各 Agent 消费者独立扩缩容

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

### 会话存储

| 层级 | 组件 | 用途 |
|------|------|------|
| 缓存 | Redis | `current_step` + 中间状态，TTL 4h |
| 持久化 | PostgreSQL | sessions 表 + agent_outputs 表 |
| 内存降级 | `InMemorySessionStore` | Redis 不可用时自动回退 |

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
| 5432 | PostgreSQL | 持久存储 |
| 6379 | Redis | 会话缓存 |
| 5672 | RabbitMQ AMQP | 消息队列 |
| 15672 | RabbitMQ UI | 管理界面 |
| 7474/7687 | Neo4j | 图数据库 |
| 8000 | OmniOps API | 主服务 |

## 环境变量（关键）

```bash
LLM_PROVIDER=openrouter        # anthropic | openai | openrouter | minimax
RABBITMQ_URL=amqp://omniops:omniops123@localhost:5672/
HITL_TIMEOUT_SECONDS=600
HITL_ESCALATION_WEBHOOK_URL=   # 企业微信等升级通知
```
