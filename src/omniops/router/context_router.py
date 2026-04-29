"""上下文路由器"""
from enum import Enum
from typing import List

from omniops.core.config import get_settings
from omniops.models import Session


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
        if hasattr(session, "perception_metadata"):
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
        if session.diagnosis_result:
            if session.diagnosis_result.confidence < 0.7:
                return True

        # 严重级别告警
        severity_map = {
            "Critical": 4,
            "Major": 3,
            "Minor": 2,
            "Warning": 1,
        }
        if hasattr(session, "perception_metadata"):
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
