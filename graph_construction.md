
---

## 一、功能定位与边界（先锁死范围）

| 维度 | 边界定义 |
|------|----------|
| **用户操作** | 上传 `.txt` / `.md` 告警知识文档 → 系统自动解析 → 构建图知识库 |
| **存储目标** | Neo4j（图结构）+ Qdrant（社区摘要向量）+ PostgreSQL（构建任务元数据） |
| **触发时机** | **仅在诊断 Agent 内部**调用图谱查询，其他 Agent 无感知 |
| **前端集成** | 新增独立"知识库"管理页 + 在诊断节点抽屉内嵌"图谱证据"标签页，与现有三栏式 UI 兼容 |
| **API 统一** | 走 `/v1/knowledge/*` 命名空间，经同一 API Gateway 转发 |
| **多库隔离** | 支持按领域隔离（`domain=optical_network`），避免与业务拓扑数据混用 |

---

## 二、GraphRAG 构建流程设计

你提供的文档已经是**高度结构化**的（实体表、关系表、规则库），因此系统需要同时支持：
1. **结构化快速通道**：识别到表格/三元组时直接解析入库
2. **非结构化兜底**：遇到自由文本时启用 LLM 提取

```
┌─────────────────────────────────────────────────────────────┐
│                    知识图谱构建流水线                         │
├─────────────────────────────────────────────────────────────┤
│  1. 文档上传 (txt/md)                                       │
│     ↓                                                       │
│  2. 文档解析器 (Document Parser)                             │
│     ├─ 结构化探测：正则提取表格、JSON 三元组 → 结构化通道      │
│     └─ 非结构化 fallback：LLM 分块提取实体/关系               │
│     ↓                                                       │
│  3. 实体归一化 (Entity Normalization)                        │
│     └─ 同义词合并："LOS告警" ↔ "R_LOS"                       │
│     ↓                                                       │
│  4. 图构建 (Neo4j Bulk Import)                               │
│     └─ MERGE 节点(Alarm/Fault/Device/Topology/Rule)           │
│     └─ MERGE 关系(6类关系 + 权重/置信度)                      │
│     ↓                                                       │
│  5. 社区检测 (Neo4j GDS / igraph)                            │
│     └─ Louvain/Leiden 算法发现"光功率异常社区"、"硬件故障社区" │
│     ↓                                                       │
│  6. 社区摘要生成 (LLM)                                       │
│     └─ 每个社区生成自然语言摘要（如诊断指南短文）              │
│     ↓                                                       │
│  7. 向量化存储 (Qdrant)                                      │
│     └─ 社区摘要、规则文本、实体描述 → Embedding                │
│     ↓                                                       │
│  8. 构建完成，前端通知                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、Neo4j 图模型 Schema（针对你的文档）

### 节点标签

```cypher
// 告警实例 (来自文档第一节)
(:Alarm {
  code: 'R_LOS',              // 唯一标识
  name: '信号丢失',
  level: '紧急',
  type: '通信',
  key_params: ['光口号'],
  device_type: 'OTU单板'
})

// 故障类型 (根因/衍生)
(:Fault {
  id: 'FAULT-002',
  name: '光纤断纤',
  category: '物理层故障',
  location_features: '光功率异常/无光',
  common_alarms: ['R_LOS', 'MUT_LOS']
})

// 网元设备
(:Device {
  type: 'OTU单板',
  id_pattern: 'OTU-A-01',
  layer: '电层',
  key_attrs: '波分侧光口、FEC模式'
})

// 拓扑链路
(:Topology {
  link_id: 'LINK-001',
  link_type: '光纤连接',
  src_node: 'OTU-A',
  dst_node: 'OTU-B'
})

// 规则节点
(:Rule {
  rule_id: 'RULE-1',
  name: '光功率异常定位链',
  content: 'IF 告警 IN {R_LOS...} THEN 逆着信号流向上游追溯...'
})

// 社区节点 (GraphRAG 特有)
(:Community {
  community_id: 'c_01',
  name: '光功率异常社区',
  summary: '该社区包含R_LOS、IN_PWR_LOW等告警，主要根因为光纤断纤、线路衰减...',
  keywords: ['光功率', 'R_LOS', '光纤'],
  node_count: 15
})
```

### 关系类型

```cypher
// 文档已定义的6类核心关系
(:Alarm)-[:IS_CAUSED_BY {confidence: 0.95, weight: '高', source: '2.50节'}]->(:Fault)
(:Alarm)-[:TRIGGERS {sequence: '先R_LOS后MS_RDI', weight: '中'}]->(:Alarm)
(:Alarm)-[:IS_LOCATED_AT {granularity: '光口级'}]->(:Device)
(:Device)-[:IS_CONNECTED_UPSTREAM {type: '波分侧光纤'}]->(:Device)
(:Device)-[:BELONGS_TO_LINK {role: '源节点'}]->(:Topology)
(:Device)-[:HAS_ALERT {condition: '接收无光'}]->(:Alarm)

// GraphRAG 新增
(:Alarm/:Fault/:Device)-[:BELONGS_TO {centrality: 0.82}]->(:Community)
(:Rule)-[:APPLIES_TO]->(:Alarm)
```

---

## 四、诊断 Agent 集成边界（核心）

诊断 Agent 的 Prompt 中新增一个**图谱感知模块**：

```python
# 诊断 Agent 内部伪代码
async def diagnose_with_kg(session_id, structured_alarms):
    # 1. 实体链接：从告警表提取关键实体
    seed_entities = extract_entities(structured_alarms)  
    # e.g., ["R_LOS", "K1SL64", "NE-BJ-01"]
    
    # 2. 调用知识图谱查询 API（新增）
    kg_result = await api.post("/v1/knowledge/graph/query", {
        "query_type": "hybrid",
        "seed_entities": seed_entities,
        "hops": 2,                          # 查2跳邻居
        "include_community_summary": True,   # 带回社区摘要
        "include_vector_similarity": True,   # 带回向量相似案例
        "include_rules": True,               # 带回匹配规则
        "top_k": 5
    })
    
    # 3. 将图谱结果注入 Prompt
    prompt = f"""
    【当前告警】
    {structured_alarms}
    
    【图谱关联知识】
    根因路径: {kg_result.subgraph_paths}        # e.g., R_LOS -[:IS_CAUSED_BY]-> 光纤断纤
    社区摘要: {kg_result.community_summaries}    # e.g., "光功率异常社区..."
    历史相似: {kg_result.vector_results}         # e.g., 案例#042
    适用规则: {kg_result.rules}                # e.g., 规则1：光功率异常定位链
    
    请基于以上信息给出根因分析...
    """
    
    return await llm.generate(prompt)
```

**关键边界**：
- 感知/方案/校验/人工审核 Agent **零改动**
- 诊断 Agent 内部只增加一个 `kg_query()` 调用，失败时优雅降级为纯向量 RAG
- 查询延迟目标：**< 500ms**（Neo4j 子图查询 + Qdrant 向量检索并行）

---

## 五、后端 API 设计（统一接入）

### 5.1 知识图谱管理 API

```http
# 1. 上传文档触发构建
POST /v1/knowledge/builds
Content-Type: multipart/form-data
file: <alarm_knowledge.txt>
domain: "optical_network"        # 领域隔离标签
build_mode: "structured_first"  # structured_first | llm_extract

Response:
{
  "build_id": "kgb_20260501_001",
  "status": "queued",
  "estimated_seconds": 120
}

# 2. 查询构建进度（前端轮询/SSE）
GET /v1/knowledge/builds/{build_id}/status

Response:
{
  "build_id": "kgb_20260501_001",
  "status": "community_detecting",  # queued → parsing → extracting → graph_building → community_detecting → summarizing → completed
  "progress": 75,
  "stats": {
    "entities": 120,
    "relations": 340,
    "communities": 8,
    "rules": 5
  }
}

# 3. 获取领域图谱元数据
GET /v1/knowledge/graphs/{domain}/metadata

# 4. 删除领域图谱
DELETE /v1/knowledge/graphs/{domain}
```

### 5.2 图谱查询 API（诊断 Agent 专用）

```http
POST /v1/knowledge/graph/query
Authorization: Bearer <service_token>

{
  "query_type": "hybrid",              # subgraph | community | path | hybrid
  "seed_entities": ["R_LOS", "K1SL64"],
  "hops": 2,
  "relation_types": ["IS_CAUSED_BY", "IS_LOCATED_AT"],
  "include_community_summary": true,
  "include_vector_similarity": true,
  "include_rules": true,
  "top_k": 5,
  "domain": "optical_network"
}

Response:
{
  "subgraph": {
    "nodes": [
      {"id": "R_LOS", "label": "Alarm", "name": "信号丢失"},
      {"id": "FAULT-002", "label": "Fault", "name": "光纤断纤"}
    ],
    "edges": [
      {"source": "R_LOS", "target": "FAULT-002", "type": "IS_CAUSED_BY", "confidence": 0.95}
    ]
  },
  "community_summaries": [
    {
      "community_id": "c_01",
      "name": "光功率异常社区",
      "summary": "该社区包含R_LOS、IN_PWR_LOW等告警，主要根因为光纤断纤、线路衰减过大、连接器污损...",
      "key_entities": ["R_LOS", "IN_PWR_LOW", "FAULT-002", "FAULT-017"]
    }
  ],
  "vector_results": [
    {
      "case_id": "case_042",
      "content": "某次K1SL64光模块老化导致链路中断...",
      "similarity_score": 0.94
    }
  ],
  "rules": [
    {
      "rule_id": "RULE-1",
      "name": "光功率异常定位链",
      "content": "IF 告警 IN {R_LOS, IN_PWR_LOW...} THEN 逆着信号流向上游追溯..."
    }
  ],
  "query_latency_ms": 320
}
```

### 5.3 可视化数据 API（前端图谱渲染）

```http
GET /v1/knowledge/graph/visualization?domain=optical_network&center=R_LOS&hops=2&layout=force

Response:
{
  "elements": {
    "nodes": [
      {"data": {"id": "R_LOS", "label": "R_LOS\n信号丢失", "type": "Alarm", "color": "#ef4444"}}
    ],
    "edges": [
      {"data": {"id": "e1", "source": "R_LOS", "target": "FAULT-002", "label": "IS_CAUSED_BY"}}
    ]
  },
  "layout": "cose",  // cytoscape 布局算法
  "style": [...]     // 预设样式
}
```

---

## 六、前端界面设计（与现有系统兼容）

### 6.1 新增页面：知识库管理 (`/dashboard/knowledge`)

与现有三栏式布局**完全兼容**，复用 `SessionList` / `DetailDrawer` 设计范式：

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: OmniOps Command Center          [知识库 🔗] [返回Agent] │
├──────────────────────┬──────────────────────────────┬─────────────┤
│                      │                              │             │
│   知识文档列表        │     中央：构建与可视化画布      │  右侧详情   │
│   + 上传区           │                              │  抽屉       │
│                      │                              │             │
│  📁 光网络告警知识    │   ┌──────────────────────┐   │             │
│     v1.2 (活跃)      │   │  📤 上传新文档        │   │  点击节点   │
│     实体:120 关系:340 │   │  或拖拽txt/md到此处    │   │  展开属性   │
│                      │   └──────────────────────┘   │             │
│  📁 传输网知识v1.0   │                              │             │
│     (归档)           │   [构建中显示进度卡片]          │             │
│                      │   ┌──────────────────────┐   │             │
│  [+ 上传新文档]       │   │  📊 构建进度           │   │             │
│                      │   │  ████████░░ 80%       │   │             │
│                      │   │  解析→提取→建图→社区→摘要│   │             │
│                      │   └──────────────────────┘   │             │
│                      │                              │             │
│                      │   [完成后显示力导向图谱]        │             │
│                      │   • 红色节点: Alarm           │             │
│                      │   • 蓝色节点: Fault           │             │
│                      │   • 绿色节点: Device          │             │
│                      │   • 黄色高亮: 社区边界         │             │
│                      │                              │             │
│                      │   ┌──────────────────────┐   │             │
│                      │   │  🔍 查询调试面板       │   │             │
│                      │   │  输入: R_LOS            │   │             │
│                      │   │  [查询]                 │   │             │
│                      │   │  结果: 光纤断纤 (0.95)   │   │             │
│                      │   │  社区: 光功率异常社区     │   │             │
│                      │   └──────────────────────┘   │             │
└──────────────────────┴──────────────────────────────┴─────────────┘
```

### 6.2 诊断节点抽屉增强（与 Agent 流水线集成）

在原有的 Agent 流水线页面，点击**诊断节点**后，右侧 `DetailDrawer` 新增 **"知识图谱"** 标签页：

```tsx
// DetailDrawer.tsx 新增内容
<Tabs defaultValue="evidence">
  <TabsList className="w-full">
    <TabsTrigger value="evidence">诊断证据</TabsTrigger>
    <TabsTrigger value="rag">相似案例</TabsTrigger>
    <TabsTrigger value="graph" className="data-[state=active]:bg-blue-100">
      🔗 知识图谱
    </TabsTrigger>
  </TabsList>
  
  <TabsContent value="graph" className="space-y-4">
    {/* 迷你子图：当前告警的2跳邻居 */}
    <MiniSubgraph 
      seedNodes={["R_LOS", "IN_PWR_LOW"]} 
      hops={2}
      height={240}
    />
    
    {/* 社区摘要卡片 */}
    <CommunityCard 
      name="光功率异常社区"
      summary="该社区包含R_LOS、IN_PWR_LOW等告警，主要根因为光纤断纤、线路衰减过大..."
      confidence={0.92}
    />
    
    {/* 触发的规则 */}
    <RuleCard 
      ruleId="RULE-1"
      name="光功率异常定位链"
      content="IF 告警 IN {R_LOS, IN_PWR_LOW...} THEN 逆着信号流向上游追溯..."
      matched={true}
    />
    
    {/* 图谱来源角标 */}
    <div className="text-xs text-muted-foreground pt-2 border-t">
      来源: 光网络告警知识库 v1.2 · Neo4j 子图查询 · 2跳
    </div>
  </TabsContent>
</Tabs>
```

### 6.3 组件清单（复用现有设计系统）

| 组件 | 来源 | 用途 |
|------|------|------|
| `UploadZone` | 复用现有 | 支持 txt/md 拖拽上传 |
| `ProgressSteps` | shadcn/ui Steps | 构建流水线进度 |
| `GraphCanvas` | `react-force-graph-2d` 或 `cytoscape-react` | 力导向图谱可视化 |
| `MiniSubgraph` | `cytoscape-react` | 诊断抽屉内嵌小图（固定2-3跳） |
| `CommunityCard` | shadcn Card + Badge | 社区摘要展示 |
| `RuleCard` | shadcn Card + Alert | 规则匹配展示 |
| `QueryTester` | shadcn Input + Button | 知识库查询调试 |

---

## 七、技术栈与部署

### 7.1 Demo 级（与现有 docker-compose 集成）

在原有 `docker-compose.yml` 中追加：

```yaml
services:
  # 原有服务...
  
  neo4j:
    image: neo4j:5.15-community
    environment:
      NEO4J_AUTH: neo4j/demo123
      NEO4J_PLUGINS: '["apoc", "gds"]'  # APOC + Graph Data Science
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    ports:
      - "7474:7474"  # Browser
      - "7687:7687"  # Bolt
  
  kg-builder:
    build: ./kg-builder  # 独立构建服务
    environment:
      NEO4J_URI: bolt://neo4j:7687
      QDRANT_URL: http://qdrant:6333
    depends_on:
      - neo4j
      - qdrant
```

### 7.2 生产级

- **Neo4j**：企业版因果集群（3 节点），或 AuraDB（托管）
- **GDS**：社区检测在 Neo4j GDS 中完成，避免数据跨网络传输
- **KG Builder**：独立 Deployment，Celery Worker 异步处理构建任务
- **向量化**：复用现有 Qdrant，新增 `kg_communities` collection

---

## 八、实施路线图（2 周落地）

| 阶段 | 周期 | 交付物 | 关键动作 |
|------|------|--------|----------|
| **Phase 1** | Week 1 | 结构化导入 + 基础可视化 | 解析你提供的文档三元组 → Neo4j 批量导入 → 前端知识库页面（上传+列表+简单查询） |
| **Phase 2** | Week 2 | GraphRAG 增强 + 诊断集成 | Neo4j GDS 社区检测 → LLM 摘要 → Qdrant 向量存储 → 诊断 Agent Prompt 注入 → 抽屉内嵌 MiniSubgraph |

---

## 九、一句话总结架构

> **知识库是"离线构建、在线查询"的独立模块：用户上传 txt/md 触发异步 GraphRAG 流水线（解析→建图→社区→摘要→向量），结果存入 Neo4j+Qdrant；诊断 Agent 在线查询时通过统一 API 获取"子图路径+社区摘要+匹配规则"，注入 Prompt 增强推理；前端通过独立知识库管理页 + 诊断节点抽屉内的迷你图谱完成交互，与现有三栏式 Agent 驾驶舱完全兼容。**
