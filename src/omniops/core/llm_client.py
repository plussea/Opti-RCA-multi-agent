"""LLM 客户端（支持 Anthropic 和 OpenAI）

.. deprecated::
    Use :func:`omniops.core.providers.get_provider` instead.
    Prompt constants have moved to :mod:`omniops.core.prompts`.
"""
import json
import logging
import re
import warnings
from typing import Any, Dict, List, Optional, cast

from anthropic import Anthropic

from omniops.core.config import get_settings
from omniops.core import prompts  # re-export for backward compat
from omniops.core.prompts import (
    DIAGNOSIS_SYSTEM_PROMPT,
    DIAGNOSIS_USER_TEMPLATE,
    PLANNING_SYSTEM_PROMPT,
    PLANNING_USER_TEMPLATE,
    get_alarm_dict_text,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端，支持 Anthropic Claude 和 OpenAI"""

    def __init__(self, provider: str = "anthropic"):
        settings = get_settings()
        self.provider = provider

        if provider == "anthropic":
            self.client: Any = Anthropic(api_key=settings.anthropic_api_key)
            self.model = settings.anthropic_model
            self.max_tokens = settings.anthropic_max_tokens
        elif provider == "openai":
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=settings.openai_api_key)
                self.model = settings.openai_model
            except ImportError:
                logger.warning("OpenAI SDK not installed, falling back to Anthropic")
                self.provider = "anthropic"
                self.client = Anthropic(api_key=settings.anthropic_api_key)
                self.model = settings.anthropic_model
                self.max_tokens = settings.anthropic_max_tokens
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        logger.info(f"LLM Client initialized with provider={provider}, model={self.model}")

    async def generate(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """生成文本回复"""
        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    system=system,
                    messages=[
                        {"role": "user", "content": user_message}
                    ],
                    temperature=temperature,
                )
                return str(response.content[0].text)

            elif self.provider == "openai":
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens or self.max_tokens,
                )
                content = response.choices[0].message.content
                return str(content) if content else ""

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

        return ""

    async def generate_json(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """生成 JSON 格式回复"""
        response_text = await self.generate(
            system=system + "\n\n请以 JSON 格式输出你的回答。",
            user_message=user_message,
            temperature=temperature,
        )

        # 尝试提取 JSON
        try:
            return cast(Dict[str, Any], json.loads(response_text))
        except json.JSONDecodeError:
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                return cast(Dict[str, Any], json.loads(json_match.group(1)))

            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                return cast(Dict[str, Any], json.loads(json_match.group(0)))

            raise ValueError(f"Failed to parse JSON from response: {response_text}") from None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """对话式生成"""
        try:
            if self.provider == "anthropic":
                anthropic_messages = []
                for msg in messages:
                    role = msg["role"]
                    if role == "system":
                        continue
                    anthropic_messages.append({
                        "role": "user" if role == "user" else "assistant",
                        "content": msg["content"],
                    })

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system or "",
                    messages=anthropic_messages,
                    temperature=temperature,
                )
                return str(response.content[0].text)

            elif self.provider == "openai":
                openai_messages: List[Dict[str, str]] = []
                if system:
                    openai_messages.append({"role": "system", "content": system})
                openai_messages.extend(messages)

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=openai_messages,
                    temperature=temperature,
                    max_tokens=self.max_tokens,
                )
                content = response.choices[0].message.content
                return str(content) if content else ""

        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            raise

        return ""


# 全局单例（延迟初始化）
_llm_client: Optional[LLMClient] = None


def get_llm_client(provider: str = "anthropic") -> LLMClient:
    """获取 LLM 客户端单例

    .. deprecated::
        Use :func:`omniops.core.providers.get_provider` instead.
    """
    warnings.warn(
        "get_llm_client() is deprecated, use get_provider() from "
        "omniops.core.providers instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(provider=provider)
    return _llm_client


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
    {{"type": "alarm", "source": "NE-BJ-01", "code": "LINK_FAIL", "time": "2026-04-28T14:23:00"}}
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


# 表头标准化 Prompt（OCR 后处理用）
OCR_POST_PROCESS_SYSTEM_PROMPT = """你是一名数据清洗专家，擅长将 OCR 提取的原始表格数据整理为标准格式。"""

OCR_POST_PROCESS_USER_TEMPLATE = """以下是从网管截图 OCR 提取的原始表格数据，可能存在表头错位、字段缺失。

原始数据：
{raw_table}

标准字段：ne_name, alarm_code, alarm_name, severity (Critical/Major/Minor/Warning), occur_time

请将数据整理为标准 JSON 格式输出。只输出 JSON，不要包含其他文字。

```json
[
  {{"ne_name": "...", "alarm_code": "...", "alarm_name": "...", "severity": "Critical", "occur_time": "2026-04-28T14:23:00"}}
]
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
