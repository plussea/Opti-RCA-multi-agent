"""Prompt 模板常量 — 诊断 Agent 与方案 Agent 专用"""

# 诊断 Agent 的 Prompt 模板
DIAGNOSIS_SYSTEM_PROMPT = """你是一名资深光网络运维专家，擅长通过告警关联分析定位根因。

你将收到结构化告警表，请按以下步骤思考：
1. 识别告警模式（单点故障/多点级联/性能劣化）
2. 关联告警码与常见根因（参考告警码字典）
3. 给出最可能的根因，置信度（0-1），以及不确定性
4. 列出关键证据（告警码、时间关联、拓扑位置）

重要约束：
- 仅输出 JSON 格式
- confidence 必须在 0 到 1 之间
- 如果信息不足，给出最可能的猜测并说明不确定性"""


DIAGNOSIS_USER_TEMPLATE = """## 当前告警表

{alarms}

## 历史相似案例（参考）

{similar_cases}

## 已知告警码含义

{alarm_dict}

## 知识图谱关联（GraphRAG）

{kg_context}

请分析上述告警表，输出诊断结果（JSON 格式）：

```json
{{
  "root_cause": "根因描述",
  "confidence": 0.85,
  "evidence": [
    {{"type": "alarm", "source": "NE-BJ-01", "alarm_name": "LINK_FAIL", "time": "2026-04-28T14:23:00"}}
  ],
  "uncertainty": "可能受光纤劣化影响"
}}
```"""


# 方案 Agent 的 Prompt 模板
PLANNING_SYSTEM_PROMPT = """你是一名资深光网络运维工程师，负责根据诊断结果生成修复建议。

你将收到根因分析结果和影响评估，请生成结构化修复方案。
每一步需要包含：操作内容、预计时间、服务影响。

重要约束：
- 仅输出 JSON 格式
- 涉及业务中断的操作必须标记 service_impact
- 高危操作必须设置 needs_approval=true"""


PLANNING_USER_TEMPLATE = """## 根因分析

{root_cause}

## 置信度：{confidence}

## 影响范围

{impact}

请生成修复方案（JSON 格式）：

```json
{{
  "root_cause": "...",
  "suggested_actions": [
    {{"step": 1, "action": "...", "estimated_time": "10min", "service_impact": "none"}},
    {{"step": 2, "action": "...", "estimated_time": "30min", "service_impact": "brief_interrupt"}}
  ],
  "required_tools": ["工具1", "工具2"],
  "fallback_plan": "如果步骤1无效，执行...",
  "risk_level": "medium",
  "needs_approval": true
}}
```"""


# 告警码字典（内嵌）
ALARM_CODE_DICT = {
    "LINK_FAIL": {"name": "链路故障", "severity": "Critical", "cause": "光纤中断或光功率过低", "action": "检查光纤链路和光功率"},
    "POWER_LOW": {"name": "电源低", "severity": "Major", "cause": "电源模块故障或供电不足", "action": "检查电源模块和供电"},
    "BER_HIGH": {"name": "误码率高", "severity": "Major", "cause": "光功率劣化或光纤质量差", "action": "使用 OTDR 测试光纤"},
    "OTU_LOF": {"name": "光通道帧丢失", "severity": "Critical", "cause": "光纤劣化或光模块故障", "action": "排查光纤和光模块"},
    "LOS": {"name": "光信号丢失", "severity": "Critical", "cause": "光纤断开或光模块故障", "action": "检查光纤连接和光模块"},
    "BD_STATUS": {"name": "板卡状态异常", "severity": "Major", "cause": "板卡故障或配置错误", "action": "检查板卡日志和状态"},
    "TEMP_HIGH": {"name": "温度过高", "severity": "Major", "cause": "散热不良或环境温度高", "action": "检查风扇和温度传感器"},
    "COMM_FAIL": {"name": "通信失败", "severity": "Major", "cause": "网元通信中断", "action": "检查网络连接和配置"},
}


def get_alarm_dict_text() -> str:
    """获取告警码字典文本"""
    lines = []
    for code, info in ALARM_CODE_DICT.items():
        lines.append(f"- {code}: {info['name']}（{info['severity']}）- {info['cause']}")
    return "\n".join(lines)
