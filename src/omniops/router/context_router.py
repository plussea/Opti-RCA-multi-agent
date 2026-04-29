"""上下文路由器"""
from enum import Enum
from typing import List

from omniops.core.config import get_settings
from omniops.models import Session, SessionStatus


class AgentMode(str, Enum):
    """Agent 运行模式"""
    SINGLE = "single"      # 单 Agent 快速诊断
    MULTI = "multi"        # 多 Agent 协作
    HUMAN_IN_LOOP = "hitl"  # 人工协同


class ContextRouter:
    """上下文路由器：根据告警特征决定 Agent 协作模式"""

    def __init__(self):
        self.settings = get_settings()

    def decide_mode(self, session: Session) -> AgentMode:
        """根据会话数据决定 Agent 模式"""
        alarm_count = len(session.structured_data)

        # 感知元数据优先
        if hasattr(session, "perception_metadata") and session.perception_metadata:
            meta = session.perception_metadata
            ne_count = meta.get("ne_count", 1)
            if ne_count > 1:
                return AgentMode.MULTI

        # 基于告警数量判断
        if alarm_count < self.settings.single_agent_threshold:
            return AgentMode.SINGLE
        elif alarm_count >= self.settings.batch_agent_threshold:
            return AgentMode.MULTI

        return AgentMode.SINGLE

    def should_trigger_hitl(self, session: Session) -> bool:
        """判断是否需要人工介入"""
        # 高危告警
        if session.diagnosis_result and session.diagnosis_result.confidence < 0.7:
            return True

        # 严重级别告警
        if hasattr(session, "perception_metadata") and session.perception_metadata:
            sev_counts = session.perception_metadata.get("severity_counts", {})
            if sev_counts.get("Critical", 0) > 0:
                return True

        return False

    def build_agent_chain(self, mode: AgentMode) -> List[str]:
        """根据模式构建 Agent 链路"""
        if mode == AgentMode.SINGLE:
            return ["perception", "diagnosis"]
        elif mode == AgentMode.MULTI:
            return ["perception", "diagnosis", "impact", "planning"]
        elif mode == AgentMode.HUMAN_IN_LOOP:
            return ["perception", "diagnosis", "impact", "planning", "verification", "approval"]
        return ["perception", "diagnosis"]

    def route_after_agent(
        self,
        session,
        completed_agent: str,
    ) -> str:
        """每次 Agent 完成后调用，决定下一步。

        状态机：
        perceived  → diagnosis → impact → planning → verification → pending_human
        diagnosing → (after completion) → route based on mode
        """
        mode = self.decide_mode(session)

        if completed_agent == "perception":
            session.current_step = "perceived"
            # Next: diagnosis
            session.status = SessionStatus.PERCEIVED
            return "diagnosis"

        elif completed_agent == "diagnosis":
            session.current_step = "diagnosing"
            session.status = SessionStatus.DIAGNOSING
            # Decide: impact (multi) or skip to planning (single)
            if mode == AgentMode.SINGLE:
                return "planning"
            return "impact"

        elif completed_agent == "impact":
            session.current_step = "planning"
            session.status = SessionStatus.PLANNING
            return "planning"

        elif completed_agent == "planning":
            session.current_step = "verifying"
            session.status = SessionStatus.VERIFYING
            return "verification"

        elif completed_agent == "verification":
            suggestion = getattr(session, "suggestion", None)
            if suggestion and suggestion.needs_approval:
                session.current_step = "pending_human"
                session.status = SessionStatus.PENDING_HUMAN
                return "human_review"
            else:
                # No HITL needed — auto-complete
                session.current_step = "resolved"
                session.status = SessionStatus.COMPLETED
                return "closure"

        elif completed_agent == "human_review":
            session.current_step = "resolving"
            feedback = getattr(session, "human_feedback", None)
            if feedback:
                if feedback.get("decision") in ("adopted", "modified"):
                    session.status = SessionStatus.APPROVED
                else:
                    session.status = SessionStatus.REJECTED
            return "closure"

        elif completed_agent == "closure":
            session.current_step = "resolved"
            session.status = SessionStatus.RESOLVED
            return "terminal"

        return "terminal"

    def decide_next_agent_after_completion(
        self,
        session,
    ) -> str:
        """通用入口：根据当前 step 决定下一步（消费 completed 事件时调用）"""
        step = session.current_step
        if step == "perceived":
            return "diagnosis"
        elif step == "diagnosing":
            mode = self.decide_mode(session)
            return "impact" if mode != AgentMode.SINGLE else "planning"
        elif step == "planning":
            return "verification"
        elif step == "verifying":
            suggestion = getattr(session, "suggestion", None)
            if suggestion and suggestion.needs_approval:
                return "human_review"
            return "closure"
        elif step == "pending_human":
            return "closure"
        elif step in ("resolving", "resolved"):
            return "terminal"
        return "terminal"
