基于你的两点简化，我将 PRD 调整为**聚焦「结构化数据驱动的故障诊断与修复建议系统」**，砍掉自动修复和多模态图表理解，保留核心 MultiAgent 协作与上下文工程。

---

# OmniOps — 结构化数据驱动的智能诊断与建议系统

## 产品需求文档 (PRD) — 精简版

**文档版本**：v1.1  
**撰写日期**：2026-04-28  
**文档状态**：简化版（去执行/去复杂多模态）

---

## 1. 文档概述

### 1.1 项目背景
运维团队每日接收大量结构化告警数据（CSV 导出、网管系统报表截图/扫描件），人工分析表格关联根因效率低下。系统需自动 ingestion 这些结构化输入，通过 MultiAgent 协作完成根因定位与修复建议生成，最终由工程师审核后手动执行。

### 1.2 简化后目标
1. **结构化输入 ingestion**：支持 CSV 文件上传 + OCR 提取图片/文档中的表格数据
2. **智能诊断**：MultiAgent 协作分析表格数据，定位根因（如链路故障、板卡告警、性能劣化）
3. **修复建议**：决策 Agent 输出结构化修复方案，**人工确认后执行**，系统不直接操控网管/设备
4. **知识沉淀**：诊断案例自动入库，支持相似故障快速召回

### 1.3 范围界定
- **包含**：CSV/表格 ingestion、OCR 表格提取、MultiAgent 诊断、修复建议生成、知识库 RAG
- **不包含**：自动执行（网管 API 调用、设备配置下发）、图表/视频/非结构化截图理解、实时监控流接入

---

## 2. 术语表

| 术语 | 定义 |
|------|------|
| **认知摘要** | Agent 间通信的标准格式，包含结论、置信度、关键证据 |
| **结构化知识** | 从 CSV/OCR 提取的标准化表格数据（如告警表、拓扑表、性能指标表） |
| **方案 Agent** | 原执行 Agent 的降级版，仅生成修复建议，不调用执行工具 |
| **共享记忆池** | 分层存储：工作记忆（当前 session）+ 短期记忆（近期诊断）+ 长期向量库 |

---

## 3. 用户场景

### 3.1 用户画像

| 角色 | 痛点 | 使用场景 |
|------|------|----------|
| **网络运维工程师** | 每日处理大量告警 CSV，人工关联拓扑困难 | 上传 CSV，获取根因分析和修复建议 |
| **现场工程师** | 收到纸质/截图版网管报表，无法直接分析 | 拍照上传，OCR 提取表格后诊断 |
| **值班主管** | 需快速判断故障影响并分派处理方案 | 查看决策 Agent 生成的结构化建议报告 |

### 3.2 核心场景

**场景 A：CSV 告警批量诊断**
1. 工程师上传网管导出的告警 CSV（含时间、网元、告警码、级别）
2. 感知 Agent 解析 CSV，统一为结构化告警表
3. 诊断 Agent 关联知识库，识别告警模式（如 `K1SL64` 板卡频繁产生 `LINK_FAIL`）
4. 影响 Agent 查询拓扑知识，评估影响链路数
5. 方案 Agent 生成建议："更换 K1SL64 板卡，倒换至备用链路 K1SL16"
6. 工程师审核建议，手动在网管系统执行倒换

**场景 B：截图报表 OCR 诊断**
1. 工程师拍摄网管界面告警列表截图上传
2. 感知 Agent OCR 提取表格（网元、告警名称、发生时间）
3. 诊断 Agent 发现多网元同时上报 `OTU_LOF`，关联知识库判定为光纤劣化
4. 方案 Agent 建议："排查 ODF 架至第 3 机房间光纤，建议 OTDR 测试"
5. 工程师携带建议前往现场排查

**场景 C：复杂关联故障（多 Agent 协商）**
1. CSV 中同时存在 `POWER_LOW` 和 `BER_HIGH`
2. 诊断 Agent A 认为光功率不足导致误码
3. 诊断 Agent B 怀疑板卡故障导致功率检测异常
4. Context Router 触发仲裁，Review Agent 综合历史案例判定为"光模块老化"
5. 方案 Agent 输出分步建议：①清洁光纤端面 ②若无效则更换光模块

---

## 4. 功能需求

### 4.1 结构化数据感知层

#### 4.1.1 CSV Ingestion
- **FG-01**：支持标准 CSV 上传，自动识别编码（UTF-8/GBK）
- **FG-02**：表头智能映射：将"网元名称/NE/网元"等异构表头统一映射为标准字段（`ne_name`, `alarm_code`, `alarm_name`, `severity`, `occur_time`）
- **FG-03**：数据清洗：空值标记、时间格式统一（ISO 8601）、告警级别标准化（Critical/Major/Minor/Warning）

#### 4.1.2 OCR 表格提取
- **FG-04**：支持 PNG/JPG/PDF 中的表格提取，输出与 CSV 同构的结构化数据
- **FG-05**：OCR 后校验：对低置信度字段（<0.85）标记为 `uncertain`，提示工程师复核
- **FG-06**：表格边界识别：支持有线表格、无线表格、网管界面截图中的列表区域提取

**技术实现**：
- OCR 引擎：PaddleOCR / EasyOCR 做文字定位 + 表格结构恢复（TableMaster/PP-Structure）
- 后处理：LLM 做表头语义校正和行数据对齐

---

### 4.2 上下文路由与调度

#### 4.2.1 智能分发
- **FG-07**：基于输入数据量路由：
  - 单条/少量告警（<5 条）→ 单 Agent 快速诊断
  - 批量告警（≥5 条）或跨网元告警 → 多 Agent 协作模式
- **FG-08**：基于告警类型路由：
  - 已知告警码（知识库命中）→ 诊断 Agent 直接匹配
  - 未知/组合告警 → 深度分析模式（多 Agent + RAG 多跳推理）

#### 4.2.2 会话管理
- **FG-09**：每个上传文件生成唯一 `session_id`
- **FG-10**：支持工程师在诊断过程中追加输入（如补充一张截图），Agent 增量更新分析

---

### 4.3 MultiAgent 协作引擎

#### 4.3.1 Agent 定义（简化后）

| Agent | 职责 | 输入 | 输出 | 工具集 |
|-------|------|------|------|--------|
| **感知 Agent** | CSV 解析 / OCR 表格提取 | CSV/图片 | 结构化告警表 | CSV 解析器, OCR 引擎, 表头映射器 |
| **诊断 Agent** | 根因分析 | 结构化告警表 + 知识库 | 根因假设 + 置信度 | RAG 检索, 规则引擎, 拓扑查询 |
| **影响 Agent** | 影响范围评估 | 根因 + 拓扑知识 | 影响网元/链路/业务列表 | 拓扑图谱查询, 业务关联表 |
| **方案 Agent** | 修复建议生成 | 根因 + 影响 | 结构化修复方案 | 方案模板库, 历史案例库 |
| **验证 Agent** | 建议合理性校验 | 修复方案 | 方案可行性评分 | 约束检查（如是否需停业务） |
| **审批 Agent** | 高危建议标记 | 修复方案 | 风险等级 + 人工审核标记 | 策略规则 |

#### 4.3.2 协作模式

**模式一：流水线模式**
```
感知 → 诊断 → 影响 → 方案 → 验证
```
- 适用：标准单网元告警，知识库有明确匹配案例

**模式二：协商模式**
```
诊断 Agent A（规则推理）─┐
                         ├→ Context Router 聚合 → 方案
诊断 Agent B（RAG 案例匹配）─┘
```
- 适用：组合告警或多网元关联故障
- 冲突解决：置信度差异 >0.2 时触发 Review Agent 仲裁

**模式三：人机协同模式**
- 触发条件：方案 Agent 建议涉及业务中断、或验证 Agent 评分 <0.7
- 流程：方案生成后暂停，推送至工程师审核界面，等待人工确认后标记 session 为 `approved` 或 `rejected`

#### 4.3.3 上下文工程（核心保留）

**认知摘要协议**（Agent 间通信标准格式）：
```json
{
  "from_agent": "diagnosis",
  "to_agent": "planning",
  "session_id": "sess_20260428_001",
  "conclusion": "K1SL64 板卡 LINK_FAIL 由光功率不足触发",
  "confidence": 0.89,
  "evidence": [
    {"type": "alarm", "source": "NE-BJ-01", "code": "LINK_FAIL", "time": "14:23"},
    {"type": "metric", "source": "OCR提取表", "field": "光功率", "value": "-28dBm"}
  ],
  "uncertainty": "未确认是光纤弯折还是光模块故障",
  "required_action": "建议排查光纤并测试光功率",
  "context_window_used": 1500
}
```

**上下文压缩策略**：
- **FG-11**：批量告警摘要：当 CSV >50 行时，按网元/告警码聚合为统计摘要（如"NE-BJ-01 共 5 条 LINK_FAIL"）
- **FG-12**：滑动窗口：保留最近 3 轮 Agent 对话，早期内容摘要化
- **FG-13**： selective sharing：方案 Agent 只接收诊断结论摘要，不接收原始告警明细

---

### 4.4 RAG 知识库系统

#### 4.4.1 知识库架构
- **向量存储**：Qdrant，存储故障案例、板卡告警含义、修复方案
- **稀疏索引**：Elasticsearch，存储告警码、网元型号、板卡类型（精确匹配）
- **知识图谱**：Neo4j，存储网元拓扑、板卡兼容性、业务路径（用于影响评估）

#### 4.4.2 检索策略
- **FG-14**：混合检索：Dense（告警描述语义）+ Sparse（告警码精确匹配），RRF 融合
- **FG-15**：查询改写：将"链路不通"改写为"LINK_FAIL 或 OTU_LOF 根因分析"
- **FG-16**：多跳推理：告警码 → 板卡类型 → 常见根因 → 标准修复流程（2-3 跳）
- **FG-17**：重排序：Cross-Encoder 对初召回案例精排，取 Top-3 最相似历史故障

#### 4.4.3 知识更新
- **FG-18**：诊断闭环入库：session 结束后，验证 Agent 提取"告警码-根因-建议"写入向量库
- **FG-19**：去重校验：新案例与现有库相似度 >0.85 时合并更新 `hit_count`，而非新增条目

---

### 4.5 方案生成与输出（替代原执行层）

#### 4.5.1 方案 Agent 设计
- **FG-20**：结构化输出：修复方案必须包含以下字段：
  ```json
  {
    "root_cause": "K1SL64 光模块老化导致收光功率不足",
    "suggested_actions": [
      {"step": 1, "action": "清洁光纤端面", "estimated_time": "10min", "service_impact": "none"},
      {"step": 2, "action": "更换 K1SL64 光模块", "estimated_time": "30min", "service_impact": "brief_interrupt"}
    ],
    "required_tools": ["光纤清洁棒", "OTDR", "备用光模块"],
    "fallback_plan": "若清洁无效，立即执行步骤 2；若仍无效，升级至板卡更换",
    "risk_level": "medium",
    "needs_approval": true
  }
  ```

#### 4.5.2 验证 Agent 校验
- **FG-21**：约束检查：校验建议是否违反已知约束（如"业务高峰期禁止中断操作"）
- **FG-22**：一致性校验：方案与诊断结论是否逻辑自洽（防止方案与根因不匹配）

#### 4.5.3 人工审核界面
- **FG-23**：方案卡片：展示结构化方案，工程师可一键"采纳"、"修改"、"拒绝"
- **FG-24**：反馈闭环：工程师执行后回填实际结果，用于评估方案 Agent 准确率

---

### 4.6 Memory 管理系统

#### 4.6.1 分层架构

| 层级 | 存储 | 内容 | TTL |
|------|------|------|-----|
| **工作记忆** | Redis | 当前 session 的原始数据 + Agent 对话 | 4 小时 |
| **短期记忆** | PostgreSQL | 近 7 天诊断 session 摘要 | 7 天 |
| **长期记忆-向量** | Qdrant | 故障案例、修复方案 | 永久 |
| **长期记忆-图谱** | Neo4j | 网元拓扑、业务路径 | 永久 |

#### 4.6.2 核心机制
- **FG-25**：上下文压缩：工作记忆 >100K tokens 时，原始告警数据转存 PG，Agent 上下文只保留摘要
- **FG-26**：记忆注入：诊断 Agent 启动时，自动将 Top-3 相似历史案例注入 System Prompt

---

## 5. 非功能需求

| 编号 | 需求 | 指标 |
|------|------|------|
| **NF-01** | 端到端延迟 | CSV <30s；OCR+诊断 <90s |
| **NF-02** | OCR 准确率 | 表格结构提取 >90%；字段识别 >95% |
| **NF-03** | 诊断准确率 | 根因判定准确率 >85%（以工程师标注为准） |
| **NF-04** | 方案采纳率 | 工程师直接采纳率 >70%（无需修改） |
| **NF-05** | 并发处理 | 支持 ≥20 个 session 同时分析 |
| **NF-06** | Token 效率 | 通过上下文压缩，相比无压缩降低 35%+ |

---

## 6. 系统架构（简化版）

```
┌─────────────────────────────────────────┐
│              接入层                      │
│  ┌──────────┐      ┌──────────────┐    │
│  │ CSV 上传 │      │ 图片/PDF 上传 │    │
│  └────┬─────┘      └──────┬───────┘    │
└───────┼───────────────────┼─────────────┘
        │                   │
┌───────▼───────────────────▼─────────────┐
│           感知 Agent (Perception)         │
│  CSV 解析器 + OCR 表格提取 (PP-Structure) │
└───────────────┬───────────────────────────┘
                │
┌───────────────▼───────────────────────────┐
│         上下文路由器 (Context Router)       │
│    分发策略：单 Agent / 多 Agent / 人工     │
└───────────────┬───────────────────────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐  ┌───▼───┐  ┌───▼───┐
│诊断Agent│  │影响Agent│  │知识检索 │
│(x2 实例)│  │(x1 实例)│  │(RAG)   │
└───┬───┘  └───┬───┘  └───┬───┘
    └───────────┼───────────┘
                │
        ┌───────▼────────┐
        │   方案 Agent     │
        │ (生成修复建议)   │
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │   验证 Agent     │
        │ (合理性校验)     │
        └───────┬────────┘
                │
    ┌───────────▼───────────┐
    │      人工审核界面       │
    │  (采纳/修改/拒绝/反馈)  │
    └───────────┬───────────┘
                │
        ┌───────▼────────┐
        │    共享记忆池     │
        │ (Redis + PG +   │
        │ Qdrant + Neo4j) │
        └────────────────┘
```

---

## 7. 接口设计

### 7.1 外部接口

**上传与诊断接口**
```http
POST /v1/sessions
Content-Type: multipart/form-data

file: <csv_or_image>
file_type: "csv" | "image" | "pdf"
topology_hint: "OTN" | "SDH" | "IP"  // 可选，辅助表头映射

Response:
{
  "session_id": "sess_20260428_001",
  "status": "analyzing",
  "estimated_seconds": 45
}
```

**获取诊断结果**
```http
GET /v1/sessions/{session_id}/result

Response:
{
  "session_id": "sess_20260428_001",
  "status": "completed",  // analyzing | completed | needs_review
  "structured_input": {
    "source": "ocr",
    "rows_extracted": 12,
    "uncertain_fields": [{"row": 3, "field": "alarm_name", "confidence": 0.72}]
  },
  "diagnosis": {
    "root_cause": "K1SL64 光模块收光功率不足（-28dBm）",
    "confidence": 0.91,
    "evidence": [...]
  },
  "impact": {
    "affected_links": ["BJ-SH-01", "BJ-GZ-03"],
    "affected_services": ["专线-金融客户A"]
  },
  "suggestion": {
    "actions": [...],
    "risk_level": "medium",
    "needs_approval": true
  },
  "similar_cases": [
    {"case_id": "case_042", "similarity": 0.94, "resolution": "更换光模块"}
  ]
}
```

**人工反馈**
```http
POST /v1/sessions/{session_id}/feedback
{
  "decision": "adopted" | "modified" | "rejected",
  "actual_action": "清洁光纤后恢复，未更换光模块",
  "effectiveness": "resolved" | "partial" | "failed"
}
```

---

## 8. 数据模型

**Session**
```json
{
  "session_id": "sess_20260428_001",
  "input_type": "csv",
  "structured_data": [{"ne_name": "NE-BJ-01", "alarm_code": "LINK_FAIL", ...}],
  "diagnosis_result": {
    "root_cause": "...",
    "confidence": 0.91,
    "agent_chain": ["perception", "diagnosis", "impact", "planning", "verification"]
  },
  "suggestion": {...},
  "human_feedback": {...},
  "created_at": "2026-04-28T14:23:00Z"
}
```

**KnowledgeEntry**
```json
{
  "entry_id": "know_001",
  "alarm_pattern": ["LINK_FAIL", "POWER_LOW"],
  "ne_type": "K1SL64",
  "root_cause": "光模块老化",
  "suggestion": {"actions": [...]},
  "source_session": "sess_20260315_042",
  "hit_count": 15,
  "effectiveness_rate": 0.93
}
```

---

## 9. 里程碑（简化后 6 周）

| 阶段 | 周期 | 目标 | 成功标准 |
|------|------|------|----------|
| **MVP** | Week 1-2 | CSV 上传 + 单 Agent 诊断 | 支持标准 CSV，根因准确率 >75% |
| **Alpha** | Week 3-4 | OCR 表格提取 + 多 Agent 协作 | 图片表格提取准确率 >90%，多 Agent 协商可用 |
| **Beta** | Week 5-6 | 方案生成 + 知识闭环 | 结构化建议采纳率 >70%，知识库自动更新 |

---

## 10. 附录

### 附录 A：OCR 后处理 Prompt 模板
```text
你是一名数据清洗专家。以下是从网管截图 OCR 提取的原始表格数据，可能存在表头错位、字段缺失。
请根据 OTN 网络告警的常识，将数据整理为标准格式，输出 JSON。
标准字段：ne_name, shelf, slot, board_type, alarm_code, alarm_name, severity, occur_time
注意：severity 只允许 Critical/Major/Minor/Warning
```

### 附录 B：诊断 Agent System Prompt 模板
```text
你是一名资深光网络/数据网络运维专家，擅长通过告警关联分析定位根因。
你将收到结构化告警表，请按以下步骤思考：
1. 识别告警模式（单点/多点/级联）
2. 关联知识库中的历史案例
3. 给出最可能的根因，置信度（0-1），以及不确定性
4. 列出关键证据（告警码、时间关联、拓扑位置）
输出必须严格遵循 JSON Schema。
```