"""上下文路由器测试"""
import pytest

from omniops.memory.store import generate_session_id
from omniops.models import AlarmRecord, Session, SessionStatus
from omniops.router.context_router import AgentMode, ContextRouter


class TestContextRouter:
    def setup_method(self):
        self.router = ContextRouter()

    def _create_session(self, alarm_count: int, ne_count: int = 1) -> Session:
        records = [
            AlarmRecord(
                ne_name=f"NE-{i:02d}",
                alarm_code="LINK_FAIL",
                alarm_name="链路故障",
            )
            for i in range(alarm_count)
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type="csv",
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )
        session.perception_metadata = {
            "alarm_count": alarm_count,
            "ne_count": ne_count,
            "severity_counts": {"Critical": alarm_count},
        }
        return session

    def test_single_agent_mode(self):
        session = self._create_session(alarm_count=3)
        mode = self.router.decide_mode(session)
        assert mode == AgentMode.SINGLE

    def test_multi_agent_mode_by_count(self):
        session = self._create_session(alarm_count=10)
        mode = self.router.decide_mode(session)
        assert mode == AgentMode.MULTI

    def test_multi_agent_mode_by_ne(self):
        session = self._create_session(alarm_count=3, ne_count=5)
        mode = self.router.decide_mode(session)
        assert mode == AgentMode.MULTI

    def test_threshold_boundary(self):
        # exactly 5 should go multi-agent (>= threshold)
        session = self._create_session(alarm_count=5)
        mode = self.router.decide_mode(session)
        assert mode == AgentMode.MULTI

    def test_build_agent_chain_single(self):
        chain = self.router.build_agent_chain(AgentMode.SINGLE)
        assert "perception" in chain
        assert "diagnosis" in chain
        assert len(chain) == 2

    def test_build_agent_chain_multi(self):
        chain = self.router.build_agent_chain(AgentMode.MULTI)
        assert "perception" in chain
        assert "diagnosis" in chain
        assert "impact" in chain
        assert "planning" in chain

    def test_build_agent_chain_hitl(self):
        chain = self.router.build_agent_chain(AgentMode.HUMAN_IN_LOOP)
        assert "verification" in chain
        assert "approval" in chain

    def test_should_trigger_hitl_low_confidence(self):
        session = self._create_session(alarm_count=3)
        session.diagnosis_result = type("obj", (), {"confidence": 0.5})()
        session.perception_metadata = {
            "alarm_count": 3,
            "ne_count": 1,
            "severity_counts": {"Major": 3},  # No Critical, rely on low confidence
        }
        assert self.router.should_trigger_hitl(session)

    def test_should_trigger_hitl_high_confidence(self):
        session = self._create_session(alarm_count=3)
        session.diagnosis_result = type("obj", (), {"confidence": 0.9})()
        # Override to non-Critical so we test confidence-only logic
        session.perception_metadata = {
            "alarm_count": 3,
            "ne_count": 1,
            "severity_counts": {"Major": 3},
        }
        assert not self.router.should_trigger_hitl(session)

    def test_should_trigger_hitl_critical(self):
        session = self._create_session(alarm_count=1)
        session.perception_metadata = {
            "alarm_count": 1,
            "ne_count": 1,
            "severity_counts": {"Critical": 1},
        }
        assert self.router.should_trigger_hitl(session)