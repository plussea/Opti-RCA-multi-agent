# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

OmniOps — 结构化数据驱动的智能诊断与建议系统。运维团队通过上传 CSV/OCR 表格数据，由 MultiAgent 协作完成根因定位与修复建议生成，工程师人工审核后执行。

## 开发环境

```bash
# 安装依赖（使用 uv）
uv sync

# 安装开发依赖
uv sync --extra dev

# 运行测试
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/unit/test_csv_parser.py -v

# 代码检查
uv run ruff check src/ tests/
uv run mypy src/

# 启动服务
uv run python -m omniops.api.main
```

## 技术栈

- **语言**: Python 3.8+（注意：typing 需用 `List/Dict/Optional` 而非内置泛型 `list[]/dict[]`）
- **API 框架**: FastAPI + Uvicorn
- **配置管理**: Pydantic Settings（`SettingsConfigDict`）
- **依赖管理**: uv + pyproject.toml
- **测试**: pytest + pytest-asyncio

## 项目结构

```
src/omniops/
├── agents/          # Agent 实现
│   ├── base.py      # BaseAgent 抽象基类
│   ├── perception.py
│   ├── diagnosis.py  # 规则推理 + 告警模式匹配
│   ├── impact.py     # 影响范围评估
│   └── planning.py   # 修复方案模板匹配
├── api/
│   ├── main.py      # FastAPI 入口
│   └── routes.py    # REST API 路由
├── core/
│   ├── config.py    # Settings 单例（lru_cache）
│   └── encoding.py  # CSV 编码检测
├── ingestion/
│   └── csv_parser.py  # CSV 摄取 + 表头标准化
├── memory/
│   └── store.py     # 会话存储（内存实现，接口预留 Redis）
├── models/
│   ├── session.py   # Session, AlarmRecord, DiagnosisResult 等
│   └── knowledge.py # CognitiveSummary 协议
└── router/
    └── context_router.py  # Agent 模式路由（SINGLE/MULTI/HITL）
```

## 关键模式

### Agent 开发
- 继承 `BaseAgent`，实现 `async process()` 方法
- 返回 `CognitiveSummary` 作为 Agent 间通信格式
- 会话状态通过 `session.xxx` 属性共享（如 `session.diagnosis_result`）

### 数据模型
- 用 `Optional[X]` 而非 `X | None`（Python 3.8 兼容性）
- 用 `List[X]` 而非 `list[X]`
- 用 `Dict[K, V]` 而非 `dict[K, V]`

### 会话存储
- `get_session_store()` 返回单例（内存实现）
- `generate_session_id()` 生成 `sess_YYYYMMDD_HHMMSS_uid` 格式 ID

## GitHub Issues

共 10 个垂直切片 issues，按依赖顺序开发：

| # | Title | 依赖 |
|---|-------|------|
| 1 | 项目脚手架与工具链 | — |
| 2 | CSV 数据摄取与标准化 | #1 |
| 3 | 单 Agent 诊断 MVP | #2 |
| 4 | RAG 知识库基础设施 | #1 |
| 5 | 知识增强诊断 | #3, #4 |
| 6 | OCR 表格提取 | #1 |
| 7 | 多 Agent 协作引擎 | #5, #6 |
| 8 | 结构化方案生成与验证 | #7 |
| 9 | 人工审核与反馈闭环 | #8 |
| 10 | 知识库自动更新 | #9 |