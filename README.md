# OmniOps

> Structured data-driven intelligent fault diagnosis and remediation suggestion system for optical network operations.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Status-Beta-orange.svg?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/Framework-FastAPI-009688.svg?style=flat-square" alt="Framework">
  <img src="https://img.shields.io/badge/MQ-RabbitMQ-ff4b4b.svg?style=flat-square" alt="MQ">
</p>

<p align="center">
  <a href="https://github.com/plussea/Opti-RCA-multi-agent">GitHub</a> ·
  <a href="http://localhost:8000/docs">API Docs</a> ·
  <a href="http://localhost:15672">RabbitMQ Dashboard</a>
</p>

---

## What is OmniOps?

OmniOps automates the root cause analysis and remediation planning for optical network alarms. Engineers upload alarm CSVs or OCR-extracted screenshots; a Multi-Agent pipeline of **Perception → Diagnosis → Impact → Planning → Verification** analyzes the fault, generates structured fix suggestions, and triggers human review for high-risk actions. After execution, the feedback loop is written back to a RAG knowledge base for continuous learning.

**No more hunting through logs.** Just upload the alarm data and get an actionable fix plan.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        OmniOps Pipeline                           │
│                                                                  │
│  CSV/OCR Upload                                                  │
│       │                                                          │
│       ▼                                                          │
│  ┌───────────┐     ┌───────────┐     ┌──────────────┐          │
│  │ Perception │────▶│  Router   │────▶│  Diagnosis   │          │
│  │   Agent    │     │ (state)   │     │   Agent     │          │
│  └───────────┘     └───────────┘     └──────┬───────┘          │
│                                             │                    │
│                                             ▼                    │
│  ┌───────────┐     ┌───────────┐     ┌──────────────┐              │
│  │  Impact   │◀────│  Router   │◀────│  Planning    │              │
│  │   Agent   │     │ (again)   │     │   Agent     │              │
│  └─────┬─────┘     └───────────┘     └──────────────┘              │
│        │                │                                       │
│        ▼                ▼                                       │
│  ┌────────────────┐  ┌──────────────────────┐                   │
│  │ Verification   │  │  Human-in-the-Loop   │                   │
│  │   Agent       │  │  (RabbitMQ + Timer)   │                   │
│  └───────┬────────┘  └──────────────────────┘                   │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────────┐                                          │
│  │  Knowledge Closure │  ← RAG vector store + feedback            │
│  └──────────────────┘                                          │
└──────────────────────────────────────────────────────────────────┘

  PostgreSQL port 5432 (pgvector), user/pass: postgres/postgres
  Redis      port 6379
  RabbitMQ   port 5672 + 15672 (ui: omniops/omniops123)
  Neo4j      port 7687
  Next.js    port 3000 (nginx 后，访问 http://localhost)
```

---

## Features

| | |
|---|---|
| **Multi-Agent Pipeline** | 5 specialized agents orchestrated by a state-machine Router with event-driven architecture |
| **光网络告警感知** | 自动解析光网络 CSV 格式（设备/告警级别/拓扑 id/定位信息），支持 MESH/RING 星型拓扑 |
| **拓扑感知推理** | 基于 Topology JSON 文件查询网元邻居、链路影响范围、业务服务 |
| **LLM-Powered Diagnosis** | Supports Anthropic, OpenAI, OpenRouter, MiniMax via a pluggable Model Registry |
| **RAG Knowledge Base** | Learns from past incidents; the more you use it, the smarter it gets |
| **Human-in-the-Loop** | High-risk actions auto-escalate to engineers via RabbitMQ; no thread blocking |
| **CSV + OCR Ingestion** | Standard CSV upload or screenshot OCR extraction from network management systems |
| **Event-Driven** | RabbitMQ decouples agents — each consumer scales independently |
| **Demo-First** | Fully functional with in-memory fallbacks; no external services required to try |

---

## Quick Start

### One-liner (demo, no services needed)

```bash
# Clone & run — everything works with in-memory storage + OpenRouter LLM
git clone https://github.com/plussea/Opti-RCA-multi-agent.git
cd Opti-RCA-multi-agent
uv sync --extra dev
uv run python demo.py
```

### Full stack (Docker)

```bash
docker compose up --build -d
# Open http://localhost          → OmniOps Command Center（Next.js 前端）
# Open http://localhost/docs     → FastAPI 文档
# Open http://localhost:15672   → RabbitMQ 管理界面（omniops/omniops123）
```

**前端架构**：`nginx` 反向代理，`NEXT_PUBLIC_API_BASE=http://nginx`，API 路由到 `omniops:8000`。前端通过 SSE（`/v1/sessions/{id}/stream`）实时接收状态更新。

---

## Demo Output

```
========================================================================
  OmniOps Multi-Agent System — Demo
========================================================================

  [Step 1] Session: sess_20260429_122935_a74f22
           5 alarms: 2 Critical / 2 Major / 1 Minor

  [Step 2] Perception → perceived
           metadata: {alarm_count: 5, ne_count: 4}

  [Step 3] Router → multi mode (≥5 alarms)
           chain: perception → diagnosis → impact → planning

  [Step 4] Agent Chain (OpenRouter LLM)

           [DIAGNOSIS] confidence=0.85
             root_cause: 光链路多处断链级联故障

           [IMPACT] 4 NEs, 4 links, 1 service affected

           [PLANNING] risk=medium, needs_approval=True
             Step 1: OTDR 测试定位衰耗点 (15min, none)
             Step 2: 倒换备用光纤 (30min, brief_interrupt)

  [Step 5] Verification → pending_human
           [FAIL] root_cause_consistency  ← LLM output mismatch
           [PASS] tools_availability
           [PASS] action_conflicts
           [PASS] action_completeness

  [Step 6] Session stored: status=pending_human
========================================================================
  Demo Complete
```

---

## API

All API endpoints are available behind nginx at `http://localhost/v1/` (or directly at `http://localhost:8000/v1/`).

### Create a diagnosis session

```bash
curl -X POST http://localhost/v1/sessions \
  -F "file=@alarms.csv"
# → {"session_id": "sess_xxx", "status": "perceived", "estimated_seconds": 60}
```

### List active sessions

```bash
curl http://localhost/v1/sessions
# → [{session_id, status, current_step, ne_count, root_cause, ...}, ...]
```

### SSE real-time stream

```bash
curl -N http://localhost/v1/sessions/{session_id}/stream --max-time 30
# → event: status\ndata: {session}\n\n  (every 1.5s until terminal status)
```

### Get diagnosis result

```bash
curl http://localhost/v1/sessions/{session_id}/result
# → {diagnosis: {root_cause, confidence, evidence}, impact: {...}, suggestion: {...}}
```

### Get agent conversations

```bash
curl http://localhost/v1/sessions/{session_id}/conversations
# → [{agent_name, step_order, tokens_used, model_name, cognitive_summary, ...}, ...]
```

### Engineer feedback

```bash
curl -X POST http://localhost/v1/sessions/{session_id}/feedback \
  -H "Content-Type: application/json" \
  -d '{"decision": "adopted", "actual_action": "已更换光纤", "effectiveness": "resolved"}'
```

---

## Configuration

Copy `.env.example` → `.env` and configure:

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxx
OPENROUTER_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free

RABBITMQ_URL=amqp://omniops:omniops123@localhost:5672/
HITL_TIMEOUT_SECONDS=600
```

All providers work out of the box: just set `LLM_PROVIDER` and the API key.

---

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests (108 passing)
uv run pytest tests/ -v

# Code quality
uv run ruff check src/ tests/
uv run mypy src/

# Add a new LLM provider — 3 steps:
#   1. Create src/omniops/core/providers/your_provider.py
#   2. Add @register("your_provider") class YourProvider(BaseProvider)
#   3. Add to _build_provider() in providers/__init__.py
```

---

## Contributing

Issues and PRs are welcome. Please:

1. Run `uv run pytest tests/` before submitting
2. Follow the existing code style (`ruff check`)
3. Add tests for new features

---

## License

MIT © 2026 OmniOps Contributors
