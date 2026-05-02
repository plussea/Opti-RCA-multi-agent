"""Agent 基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from omniops.models import CognitiveSummary, Session


class BaseAgent(ABC):
    """Agent 基类

    提供：
    - build_summary(): 标准 CognitiveSummary 构造
    - call_llm(): 标准化 LLM 调用（含超时 / 降级处理）
    """

    name: str = "base"

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name

    @abstractmethod
    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """处理输入，输出认知摘要"""
        ...

    # --------------------------------------------------------------
    # 深化的通用行为（供所有 concrete agent 调用）
    # --------------------------------------------------------------

    def build_summary(
        self,
        session: Session,
        conclusion: str,
        confidence: float,
        evidence: Optional[List[Dict[str, Any]]] = None,
        to_agent: str = "next",
        required_action: str = "",
        uncertainty: Optional[str] = None,
    ) -> CognitiveSummary:
        """标准 CognitiveSummary 构造 — 所有 Agent 共用"""
        return CognitiveSummary(
            from_agent=self.name,
            to_agent=to_agent,
            session_id=session.session_id,
            conclusion=conclusion,
            confidence=confidence,
            evidence=evidence or [],
            uncertainty=uncertainty,
            required_action=required_action,
            context_window_used=0,
        )

    async def call_llm_json(
        self,
        system: str,
        user_message: str,
        *,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """标准化 LLM JSON 调用 — 带 provider 自动探测和 best-effort 降级"""
        from omniops.core.providers import get_provider

        try:
            get_provider()  # 探测是否配置了 provider
        except Exception:
            return {}  # 无 provider，直接降级

        try:
            provider = get_provider()
            return await provider.generate_json(
                system=system,
                user_message=user_message,
                temperature=temperature,
            )
        except Exception as exc:
            return {}

    async def invoke(self, session: Session, **kwargs: Any) -> Dict[str, Any]:
        """调用 Agent，返回完整结果字典（由 router 层使用）"""
        summary = await self.process(session, kwargs)
        return {
            "agent": self.name,
            "summary": summary.model_dump(),
            "status": "success",
        }

    def _build_system_prompt(self, template: str, **kwargs: Any) -> str:
        """填充 Prompt 模板"""
        return template.format(**kwargs)
