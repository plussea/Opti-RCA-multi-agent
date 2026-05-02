"""数据库模型层"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from omniops.core.database import Base


class SessionModel(Base):
    """会话表"""
    __tablename__ = "sessions"

    session_id = Column(String(50), primary_key=True)
    input_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="analyzing")
    structured_data = Column(JSON, default=list)
    diagnosis_result = Column(JSON, nullable=True)
    impact = Column(JSON, nullable=True)
    suggestion = Column(JSON, nullable=True)
    human_feedback = Column(JSON, nullable=True)
    perception_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    alarm_records = relationship("AlarmRecordModel", back_populates="session", cascade="all, delete-orphan")
    feedback_records = relationship("FeedbackModel", back_populates="session", cascade="all, delete-orphan")
    conversations = relationship("AgentConversationModel", back_populates="session", cascade="all, delete-orphan", order_by="AgentConversationModel.step_order")


class AlarmRecordModel(Base):
    """告警记录表"""
    __tablename__ = "alarm_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    ne_name = Column(String(100), nullable=False)
    alarm_code = Column(String(50), nullable=True)
    alarm_name = Column(String(200), nullable=True)
    severity = Column(String(20), nullable=True)
    occur_time = Column(DateTime, nullable=True)
    shelf = Column(String(50), nullable=True)
    slot = Column(String(50), nullable=True)
    board_type = Column(String(100), nullable=True)
    topology_id = Column(String(100), nullable=True)  # 光网络拓扑 ID
    location = Column(String(500), nullable=True)      # 设备定位信息
    raw_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SessionModel", back_populates="alarm_records")


class KnowledgeEntryModel(Base):
    """知识库条目表"""
    __tablename__ = "knowledge_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(String(50), unique=True, nullable=False)
    alarm_pattern = Column(JSON, default=list)  # ["LINK_FAIL", "POWER_LOW"]
    ne_type = Column(String(100), nullable=True)
    root_cause = Column(Text, nullable=False)
    suggested_actions = Column(JSON, default=list)
    required_tools = Column(JSON, default=list)
    fallback_plan = Column(Text, nullable=True)
    risk_level = Column(String(20), default="low")
    source_session = Column(String(50), nullable=True)
    hit_count = Column(Integer, default=0)
    effectiveness_rate = Column(Float, default=0.0)
    embedding = Column(JSON, nullable=True)  # 存储向量
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FeedbackModel(Base):
    """反馈记录表"""
    __tablename__ = "feedback_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    decision = Column(String(20), nullable=False)  # adopted, modified, rejected
    actual_action = Column(Text, nullable=True)
    effectiveness = Column(String(20), nullable=True)  # resolved, partial, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SessionModel", back_populates="feedback_records")


class AlarmCodeDictModel(Base):
    """告警码字典表"""
    __tablename__ = "alarm_code_dict"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_code = Column(String(50), unique=True, nullable=False)
    alarm_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=True)
    common_cause = Column(Text, nullable=True)
    suggested_action = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentConversationModel(Base):
    """Agent 对话记录表 — 存储每个 Agent 的输入/输出/思考链"""
    __tablename__ = "agent_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(50), nullable=False)  # perception / diagnosis / impact / planning / verification
    step_order = Column(Integer, nullable=False)  # 执行顺序序号
    llm_input = Column(JSON, nullable=True)  # LLM 输入（结构化 prompt）
    llm_output = Column(JSON, nullable=True)  # LLM 原始输出
    cognitive_summary = Column(JSON, nullable=True)  # CognitiveSummary 结构化摘要
    tokens_used = Column(Integer, nullable=True)  # Token 消耗
    model_name = Column(String(100), nullable=True)  # 使用的模型名
    duration_ms = Column(Integer, nullable=True)  # 耗时（毫秒）
    error_message = Column(Text, nullable=True)  # 错误信息
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SessionModel", back_populates="conversations")


class KnowledgeEmbeddingModel(Base):
    """知识库向量表 — pgvector 实现（替代 SQLite）"""
    __tablename__ = "knowledge_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(50), nullable=True)  # 来源 session（可选）
    entry_id = Column(String(50), unique=True, nullable=False)
    alarm_pattern = Column(JSON, default=list)  # ["LINK_FAIL", "POWER_LOW"]
    root_cause = Column(Text, nullable=False)
    suggested_actions = Column(JSON, default=list)
    required_tools = Column(JSON, default=list)
    fallback_plan = Column(Text, nullable=True)
    risk_level = Column(String(20), default="low")
    hit_count = Column(Integer, default=0)
    effectiveness_rate = Column(Float, default=0.0)
    embedding_dim = Column(Integer, default=1536)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # NOTE: 向量列在迁移脚本中添加，SQLAlchemy 只管理标量列
    # 迁移: ALTER TABLE knowledge_embeddings ADD COLUMN embedding vector(1536);
