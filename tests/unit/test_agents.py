"""Agent 测试"""
import pytest

from omniops.agents import DiagnosisAgent, ImpactAgent, PerceptionAgent, PlanningAgent
from omniops.memory.store import generate_session_id
from omniops.models import AlarmRecord, InputType, Session, SessionStatus


class TestPerceptionAgent:
    @pytest.mark.asyncio
    async def test_process_creates_metadata(self):
        records = [
            AlarmRecord(ne_name="NE-01", alarm_name="LINK_FAIL"),
            AlarmRecord(ne_name="NE-02", alarm_name="LINK_FAIL"),
            AlarmRecord(ne_name="NE-01", alarm_name="POWER_LOW"),
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )

        agent = PerceptionAgent()
        summary = await agent.process(session)

        assert summary.from_agent == "perception"
        assert summary.to_agent == "router"
        assert session.perception_metadata["alarm_count"] == 3
        assert session.perception_metadata["ne_count"] == 2


class TestDiagnosisAgent:
    @pytest.mark.asyncio
    async def test_rule_based_diagnosis_link_fail(self):
        records = [
            AlarmRecord(ne_name="NE-01", alarm_name="OTS_LOS"),
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )

        agent = DiagnosisAgent()
        summary = await agent.process(session)

        assert "光" in summary.conclusion
        assert summary.confidence >= 0.6
        assert session.diagnosis_result is not None

    @pytest.mark.asyncio
    async def test_rule_based_diagnosis_power_low(self):
        records = [
            AlarmRecord(ne_name="NE-01", alarm_name="LSR_WILL_DIE"),
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )

        agent = DiagnosisAgent()
        summary = await agent.process(session)

        assert "光模块" in summary.conclusion
        assert summary.confidence >= 0.6


class TestImpactAgent:
    @pytest.mark.asyncio
    async def test_impact_evaluation(self):
        records = [
            AlarmRecord(ne_name="NE-01", alarm_name="LINK_FAIL"),
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )
        session.diagnosis_result = type("obj", (), {
            "root_cause": "光链路故障",
            "confidence": 0.85,
        })()

        agent = ImpactAgent()
        await agent.process(session)

        assert session.impact is not None
        assert len(session.impact.affected_ne) == 1
        assert len(session.impact.affected_links) > 0


class TestPlanningAgent:
    @pytest.mark.asyncio
    async def test_generates_structured_suggestion(self):
        records = [
            AlarmRecord(ne_name="NE-01", alarm_name="LINK_FAIL"),
        ]
        session = Session(
            session_id=generate_session_id(),
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
        )
        session.diagnosis_result = type("obj", (), {
            "root_cause": "光链路故障",
            "confidence": 0.85,
        })()

        agent = PlanningAgent()
        await agent.process(session)

        assert session.suggestion is not None
        assert len(session.suggestion.suggested_actions) > 0
        assert session.suggestion.root_cause == "光链路故障"
        assert session.suggestion.risk_level in ("low", "medium", "high")
