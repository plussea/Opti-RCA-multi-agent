"""All event schemas for the OmniOps event bus"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """All events inherit from this"""
    event_type: str
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ── Pipeline events ────────────────────────────────────────────────────────────

class DiagnosisRequestedEvent(BaseEvent):
    """诊断 Agent 待处理"""
    event_type: str = "diagnosis_requested"
    alarm_names: List[str] = Field(default_factory=list)
    structured_data: List[Dict[str, Any]] = Field(default_factory=list)
    priority: int = 1


class DiagnosisCompletedEvent(BaseEvent):
    """诊断 Agent 完成"""
    event_type: str = "diagnosis_completed"
    confidence: float = 0.0
    root_cause_summary: str = ""
    uncertainty: Optional[str] = None
    next_agent: str = "impact"  # router guidance


class ImpactRequestedEvent(BaseEvent):
    """影响 Agent 待处理"""
    event_type: str = "impact_requested"
    root_cause: str = ""
    confidence: float = 0.0


class PlanningRequestedEvent(BaseEvent):
    """方案 Agent 待处理"""
    event_type: str = "planning_requested"
    root_cause: str = ""
    confidence: float = 0.0
    impact_summary: Optional[Dict[str, Any]] = None


class PlanningCompletedEvent(BaseEvent):
    """方案 Agent 完成"""
    event_type: str = "planning_completed"
    risk_level: str = "low"
    needs_human: bool = False
    next_agent: str = "verification"


class VerificationRequestedEvent(BaseEvent):
    """校验 Agent 待处理"""
    event_type: str = "verification_requested"
    root_cause: str = ""
    suggestion_summary: Optional[Dict[str, Any]] = None
    diagnosis_summary: Optional[Dict[str, Any]] = None


class VerificationResultEvent(BaseEvent):
    """校验 Agent 结果"""
    event_type: str = "verification_result"
    passed: bool = False
    failed_checks: List[Dict[str, Any]] = Field(default_factory=list)
    next_step: str = "pending_human"  # or "failed"


class HumanReviewRequiredEvent(BaseEvent):
    """需要人工审核"""
    event_type: str = "human_review_required"
    timeout_seconds: int = 600
    timeout_at: Optional[datetime] = None
    summary_for_engineer: str = ""
    risk_level: str = "low"


class HumanFeedbackReceivedEvent(BaseEvent):
    """人工反馈已收到"""
    event_type: str = "human_feedback_received"
    decision: str = "adopted"      # adopted | modified | rejected
    actual_action: str = ""
    effectiveness: str = "resolved"  # resolved | partial | failed


class KnowledgeClosureRequestedEvent(BaseEvent):
    """知识闭环待处理"""
    event_type: str = "knowledge_closure_requested"
    root_cause: str = ""
    alarm_names: List[str] = Field(default_factory=list)
    suggested_actions: List[Dict[str, Any]] = Field(default_factory=list)
    feedback: Optional[Dict[str, Any]] = None


class SessionResolvedEvent(BaseEvent):
    """会话已终结（终态事件）"""
    event_type: str = "session_resolved"
    final_status: str = "resolved"
    mttr_seconds: Optional[int] = None
