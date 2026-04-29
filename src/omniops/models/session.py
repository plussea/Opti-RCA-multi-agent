"""会话数据模型"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InputType(str, Enum):
    CSV = "csv"
    IMAGE = "image"
    PDF = "pdf"


class SessionStatus(str, Enum):
    # --- pipeline stages ---
    PERCEIVED = "perceived"     # 感知完成，等待路由
    DIAGNOSING = "diagnosing"   # 诊断中
    PLANNING = "planning"        # 方案生成中
    VERIFYING = "verifying"     # 校验中
    PENDING_HUMAN = "pending_human"  # 等待人工审核（MQ挂起）
    # --- outcomes ---
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"       # 知识沉淀后关闭
    COMPLETED = "completed"      # 无需HITL，自动完成
    FAILED = "failed"            # 失败
    ESCALATED = "escalated"     # 人工审核超时
    # --- legacy aliases (for backward compat) ---
    ANALYZING = "analyzing"
    NEEDS_REVIEW = "needs_review"


class Severity(str, Enum):
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    WARNING = "Warning"


class AlarmRecord(BaseModel):
    """标准化告警记录"""
    ne_name: str = Field(..., description="网元名称")
    alarm_code: Optional[str] = Field(None, description="告警码")
    alarm_name: Optional[str] = Field(None, description="告警名称")
    severity: Optional[Severity] = Field(None, description="告警级别")
    occur_time: Optional[datetime] = Field(None, description="发生时间")
    shelf: Optional[str] = Field(None, description="机架")
    slot: Optional[str] = Field(None, description="槽位")
    board_type: Optional[str] = Field(None, description="板卡类型")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="原始数据")


class StructuredInput(BaseModel):
    """结构化输入"""
    source: InputType
    rows_extracted: int
    uncertain_fields: List[Dict[str, Any]] = Field(default_factory=list)


class Evidence(BaseModel):
    """证据"""
    type: str
    source: str
    code: Optional[str] = None
    field: Optional[str] = None
    value: Optional[str] = None
    time: Optional[str] = None


class DiagnosisResult(BaseModel):
    """诊断结果"""
    root_cause: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    agent_chain: List[str] = Field(default_factory=list)


class SuggestionAction(BaseModel):
    """修复建议步骤"""
    step: int
    action: str
    estimated_time: Optional[str] = None
    service_impact: Optional[str] = None


class Suggestion(BaseModel):
    """修复建议"""
    root_cause: str
    suggested_actions: List[SuggestionAction]
    required_tools: List[str] = Field(default_factory=list)
    fallback_plan: Optional[str] = None
    risk_level: str = "low"
    needs_approval: bool = False


class SimilarCase(BaseModel):
    """相似案例"""
    case_id: str
    similarity: float
    resolution: str


class Impact(BaseModel):
    """影响范围"""
    affected_links: List[str] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)
    affected_ne: List[str] = Field(default_factory=list)


class Session(BaseModel):
    """诊断会话"""
    session_id: str
    input_type: InputType
    structured_data: List[AlarmRecord] = Field(default_factory=list)
    diagnosis_result: Optional[DiagnosisResult] = None
    impact: Optional[Impact] = None
    suggestion: Optional[Suggestion] = None
    human_feedback: Optional[Dict[str, Any]] = None
    perception_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="感知层元数据（告警数量、网元数量、严重级别分布）",
    )
    status: SessionStatus = SessionStatus.ANALYZING
    current_step: str = Field(
        default="init",
        description="当前流水线步骤：init/perceived/diagnosing/planning/verifying/pending_human/resolved",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionCreateResponse(BaseModel):
    """创建会话响应"""
    session_id: str
    status: SessionStatus
    estimated_seconds: int


class FeedbackDecision(str, Enum):
    ADOPTED = "adopted"
    MODIFIED = "modified"
    REJECTED = "rejected"


class FeedbackEffectiveness(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    FAILED = "failed"


class FeedbackRequest(BaseModel):
    """反馈请求"""
    decision: FeedbackDecision
    actual_action: str
    effectiveness: FeedbackEffectiveness