"""Agent 基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from omniops.models import CognitiveSummary, Session


class BaseAgent(ABC):
    """Agent 基类"""

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