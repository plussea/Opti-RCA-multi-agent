"""认知摘要协议 — Agent 间通信标准格式"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CognitiveSummary(BaseModel):
    """Agent 间通信的标准格式"""
    from_agent: str
    to_agent: str
    session_id: str
    conclusion: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    required_action: Optional[str] = None
    context_window_used: int = 0

    def to_llm_message(self) -> str:
        """转换为 LLM 友好的消息格式"""
        evidence_str = "\n".join(
            f"- [{e.get('type')}] {e.get('source', 'unknown')}: "
            f"{e.get('code', e.get('field', ''))} = {e.get('value', e.get('time', ''))}"
            for e in self.evidence
        )
        return (
            f"From: {self.from_agent}\n"
            f"Conclusion: {self.conclusion} (confidence: {self.confidence})\n"
            f"Evidence:\n{evidence_str}\n"
            f"Uncertainty: {self.uncertainty or 'None'}\n"
            f"Required action: {self.required_action or 'N/A'}"
        )
