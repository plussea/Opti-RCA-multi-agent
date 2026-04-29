下面是一个**具体的光网络告警案例**，把数据在每个组件里的流动讲清楚。

---

## 先确认流程：加上"异步"和"闭环"

你描述的流程：

```
CSV输入 → 感知Agent → Context Router → 诊断Agent → 方案Agent → 校验Agent → 人工审核
```

**这个顺序是对的**，但生产环境中必须变成**"状态机 + 事件驱动"**，而不是函数链式调用。完善后：

```
CSV输入 
  → [感知Agent] 结构化清洗 
    → [Context Router] 写状态机(redis/pg)，发事件到MQ
      → [诊断Agent] 消费MQ事件，查向量库/图库，写根因回状态
        → [Context Router] 再次路由
          → [方案Agent] 消费事件，生成建议
            → [校验Agent] 校验合理性
              → [Context Router] 标记为"pending_human"
                → [MQ: 人工审核事件] 
                  → 工程师前端收到通知
                    → [人工确认/修改/拒绝]
                      → [验证Agent/知识沉淀] 写回向量库(PG)
                        → [Session结束]
```

**关键修正点**：
1. **Context Router 不是一次性的**，每次 Agent 完成后都回到 Router，由 Router 决定下一步（类似 CPU 调度器）
2. **人工审核是阻塞节点**：必须走 MQ，系统不能挂起等待
3. **缺少"反馈闭环"**：人工执行后的实际结果，要回流到系统中，用于更新知识库

---

## 用一个真实案例跑通全流程

**案例**：工程师上传 `alarm_20260429.csv`，内容：

| occur_time | ne_name | shelf | slot | board_type | alarm_code | alarm_name | severity |
|---|---|---|---|---|---|---|---|
| 14:23:05 | NE-BJ-01 | 1 | 3 | K1SL64 | LINK_FAIL | 光链路中断 | Critical |
| 14:23:12 | NE-SH-02 | 2 | 5 | K1SL64 | OTU_LOF | OTU帧丢失 | Critical |
| 14:24:00 | NE-BJ-01 | 1 | 3 | K1SL64 | POWER_LOW | 光功率低 | Major |

---

### Step 1：感知 Agent（Perception）

**做什么**：读取 CSV，表头映射，数据清洗，空值处理。

**数据流向**：
- **PostgreSQL**：写入 `sessions` 表（session_id, status='perceived'），写入 `structured_alarms` 表（3 条告警记录）
- **Redis**：写入工作记忆 `session:001:working_memory`，包含原始告警 JSON（TTL 4h）
- **对象存储（MinIO/本地）**：CSV 原文件归档（`uploads/2026/04/29/alarm_001.csv`）

**此时**：
- 关系库（PG）：有了"账本记录"
- Redis：有了"临时工作台"
- 向量库/图库：**还没被触碰**

---

### Step 2：Context Router（第一次调度）

**做什么**：读取 Redis 中的 session 状态，判断路由策略。

**逻辑**：
- 告警条数 = 3，跨网元（BJ 和 SH），且包含关联码（LINK_FAIL + OTU_LOF）
- **决策**：走"多 Agent 协作模式"，先发给诊断 Agent

**数据流向**：
- **Redis**：更新状态 `session:001:status = 'diagnosing'`，加乐观锁（version=1）
- **消息队列（MQ）**：发送事件到 `diagnosis_queue`：
  ```json
  {"session_id":"001","trigger":"cross_ne_alarm","priority":2}
  ```

**为什么用 MQ？**
因为诊断 Agent 可能有 3 个实例在跑，MQ 做负载均衡。如果直接函数调用，一个实例卡死就全堵死。

---

### Step 3：诊断 Agent（Diagnosis）

**做什么**：根因分析。这是**最重的环节**，会同时用到三种数据库。

**数据读取**：
1. **Redis**：读取 `session:001:working_memory`，拿到 3 条结构化告警
2. **向量库（Qdrant）**：发起 RAG 查询：
   - Query = `"LINK_FAIL K1SL64 POWER_LOW OTU_LOF 根因"`
   - 召回 Top-5 历史案例（比如案例 #42：某次 K1SL64 光模块老化导致链路中断）
3. **图库（Neo4j）**：查询拓扑关系：
   ```cypher
   MATCH (a:NE {name:'NE-BJ-01'})-[:LINK_TO]-(b:NE {name:'NE-SH-02'})
   RETURN a, b, r.fiber_id
   ```
   - 发现 BJ 和 SH 之间通过 **光纤链路 F-BJ-SH-01** 直连

**推理过程**：
- RAG 返回：K1SL64 + LINK_FAIL + POWER_LOW → 历史 85% 案例是"光模块收光功率不足"
- 图库返回：两网元在同一物理链路上，且同时告警 → 可能是**中间光纤劣化**，而非两块板卡同时坏
- 综合结论：**光纤 F-BJ-SH-01 劣化导致两端同时收光不足**

**数据写入**：
- **Redis**：写入诊断结论 `session:001:diagnosis = {...}`（置信度 0.91）
- **PostgreSQL**：写入 `agent_outputs` 表（记录哪个 Agent 做了什么，用于审计）
- **消息队列**：发送事件到 `planning_queue`，通知方案 Agent 可以开工

---

### Step 4：方案 Agent（Planning）

**做什么**：基于根因生成修复建议。

**数据读取**：
- **Redis**：读取诊断结论（不读原始告警，只读认知摘要）
- **PostgreSQL**：查询 `solution_templates` 表（光纤劣化的标准处理 SOP）

**生成方案**：
```json
{
  "root_cause": "光纤 F-BJ-SH-01 劣化，衰耗过大",
  "actions": [
    {"step":1, "action":"OTDR测试 F-BJ-SH-01，定位衰耗点", "impact":"无中断"},
    {"step":2, "action":"若衰耗>25dB，倒换至备用光纤 F-BJ-SH-02", "impact":"瞬断<50ms"}
  ],
  "risk_level": "medium",
  "needs_approval": true
}
```

**数据写入**：
- **Redis**：`session:001:suggestion = {...}`
- **MQ**：发送到 `verification_queue`

---

### Step 5：校验 Agent（Verification）

**做什么**：检查方案是否合理，是否与诊断自洽。

**校验逻辑**：
- 检查：方案里的 `root_cause` 与诊断 Agent 的 `conclusion` 是否一致？→ 一致 ✓
- 检查：步骤 2 提到的备用光纤 `F-BJ-SH-02` 是否在图库中存在且健康？
  - **Neo4j 查询**：`MATCH (f:Fiber {id:'F-BJ-SH-02'}) RETURN f.status` → `healthy` ✓
- 检查：风险等级为 medium，按策略必须人工审核 → 标记 `needs_human = true`

**数据写入**：
- **Redis**：更新 `session:001:status = 'pending_human'`
- **MQ**：发送**人工审核事件**到 `human_review_queue`（这是一个慢队列，可能阻塞很久）

---

### Step 6：人工审核（Human-in-the-Loop）

**这是最关键的区别**：系统**不能阻塞等待**人回复。

**数据流**：
1. **MQ**：`human_review_queue` 中积压着事件 `{"session_id":"001","timeout_at":"14:35:00"}`
2. **Redis**：`session:001:human_task` 标记为待处理
3. **前端**：WebSocket / SSE 推送通知给值班工程师："NE-BJ-01 光纤劣化，建议 OTDR 测试 + 倒换，请确认"
4. **工程师操作**：
   - 点击"采纳" → 前端调用 API → 系统收到回调
   - 或点击"修改"：改为"先清洁端面再 OTDR" → 系统更新方案
   - 或**超时 10 分钟未响应** → MQ 死信队列触发，标记 `escalated`，发短信给主管

**人工反馈后**：
- **PostgreSQL**：写入 `human_decisions` 表（审计需要）
- **Redis**：更新状态 `session:001:status = 'approved'`
- **MQ**：发送事件到 `closure_queue`，触发知识沉淀

---

### Step 7：知识沉淀（Closure）

**做什么**：把这次成功案例写成经验，喂给向量库。

**数据流**：
- 从 **PostgreSQL** 读取完整 session 记录（告警 + 诊断 + 方案 + 人工反馈）
- 提炼为知识条目：`"K1SL64 LINK_FAIL POWER_LOW OTU_LOF 跨网元 → 光纤劣化 → OTDR+倒换"`
- 向量化后写入 **Qdrant**（长期记忆）
- 如果人工反馈是"修改后采纳"，则更新权重，下次 RAG 优先推荐此案例
- **PostgreSQL**：`sessions` 表状态改为 `resolved`，记录 `mttr_seconds`

---

## 你的核心疑惑：各组件到底是干嘛的？

### 三种数据库的分工

| 数据库 | 在这个流程中的**具体作用** | 如果不存在会怎样？ |
|--------|--------------------------|-------------------|
| **关系库（PostgreSQL）** | **"账本/档案室"**。记录 session 生命周期、每条告警原始数据、每个 Agent 的输出日志、人工审核记录、审计追踪。**强一致，永久保存。** | 系统崩溃后无法恢复 session；无法做月度报表（本月处理了多少 LINK_FAIL）；无法审计谁改了方案 |
| **向量库（Qdrant）** | **"经验大脑/案例库"**。诊断 Agent  Step 3 时，把当前告警向量化，去库里找"历史上最像这次故障的案例"，返回根因和修复方法。**只读为主，诊断结束后写回新案例。** | 每次诊断都像新手，无法利用历史经验；K1SL64 的 LINK_FAIL 每次都要重新推理 |
| **图库（Neo4j）** | **"网络地图"**。存储网元、板卡、光纤、业务路径的拓扑关系。诊断 Agent 用它做**跨网元关联**（BJ 和 SH 是否在同一条光纤上？），校验 Agent 用它检查备用资源是否存在。**解决"空间关联"问题。** | 无法判断告警是单点故障还是链路级故障；无法评估倒换方案是否可行（不知道备用光纤在哪） |

**一句话总结**：
- **PG 记"发生了什么"**
- **向量库记"以前怎么解决的"**
- **图库记"东西在哪、怎么连的"**

---

### Redis 的作用

Redis 在这个流程里不是"缓存数据库"那么简单，它是**Agent 的"工作台 + 状态机 + 协调器"**：

| 用途 | 流程中的体现 | 为什么不用 PG？ |
|------|------------|---------------|
| **工作记忆** | `session:001:working_memory` 存当前上下文 | PG 太慢（10ms vs Redis 1ms），Agent 每轮推理都要读 |
| **分布式状态机** | `session:001:status` 从 diagnosing → pending_human → approved | 多个 Agent 实例并发读写，需要原子操作和乐观锁 |
| **实体记忆** | `entity:NE-BJ-01:health = degraded`（实时更新） | 网元状态变化快，不需要落盘持久化 |
| **限流/防重** | 同一 CSV 5 秒内重复上传？Redis `SETNX` 拒绝 | PG 唯一索引也能做，但 Redis 更轻 |
| **人工审核锁** | `human_lock:001` 防止两个工程师同时审同一个 session | 需要 TTL 自动释放，Redis 原生支持 |

---

### 消息队列（MQ）的作用

MQ 不是"传数据的"，而是**"解耦时间"**的：

| 场景 | 不用 MQ（函数调用） | 用 MQ（事件驱动） |
|------|-------------------|------------------|
| 诊断 Agent 处理 | 感知 Agent 直接 `await diagnosis_agent.run()`，如果诊断 Agent 卡了 30 秒，感知 Agent 也挂 30 秒 | 感知 Agent 发完消息立刻返回。诊断 Agent 慢慢消费，不影响上游 |
| 人工审核 | 方案 Agent `await human_review()`，如果工程师去吃饭了，线程挂起 2 小时，内存泄漏 | 方案 Agent 发完事件就结束。工程师 2 小时后点击"采纳"，MQ 唤醒后续流程 |
| 并发扩容 | 10 个 session 同时来，只能串行处理 | 10 个事件进队列，3 个诊断 Agent 实例并行消费 |
| 服务重启 | 感知 Agent 重启，正在处理的诊断任务丢失 | MQ 持久化，重启后从断点继续消费 |

**在这个流程里，MQ 传递的不是"原始数据"**，而是**"状态变更事件"**：
```json
{"event":"diagnosis_completed","session_id":"001","next_agent":"planning"}
```

原始数据都在 Redis/PG 里，MQ 只传"指针 + 指令"。

---

## 一句话总结流程

> **CSV 进来，PG 记账，Redis 当工作台，感知 Agent 洗完数据丢进 MQ；诊断 Agent 从 MQ 接到指令，去向量库查经验、去图库查地图，推理完把结论写回 Redis 再丢进 MQ；方案 Agent 和校验 Agent 接力；最后人工审核节点通过 MQ 挂起等待人回复；人确认后，整套经验写入向量库，PG 关账。**
