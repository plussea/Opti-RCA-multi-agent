"""Tests for event schemas and serialization"""
from datetime import datetime

from omniops.events.schemas import (
    DiagnosisCompletedEvent,
    DiagnosisRequestedEvent,
    HumanFeedbackReceivedEvent,
    HumanReviewRequiredEvent,
    KnowledgeClosureRequestedEvent,
    SessionResolvedEvent,
)


class TestEventSchemas:
    def test_diagnosis_requested_roundtrip(self):
        event = DiagnosisRequestedEvent(
            session_id="sess_001",
            alarm_names=["LINK_FAIL", "OTU_LOF"],
            structured_data=[{"ne_name": "NE-01", "alarm_name": "LINK_FAIL"}],
            priority=2,
        )
        data = event.model_dump()
        restored = DiagnosisRequestedEvent(**data)
        assert restored.session_id == "sess_001"
        assert restored.alarm_names == ["LINK_FAIL", "OTU_LOF"]
        assert restored.priority == 2

    def test_diagnosis_completed_roundtrip(self):
        event = DiagnosisCompletedEvent(
            session_id="sess_001",
            confidence=0.91,
            root_cause_summary="光纤劣化",
            uncertainty="可能受环境温度影响",
            next_agent="impact",
        )
        data = event.model_dump()
        restored = DiagnosisCompletedEvent(**data)
        assert restored.confidence == 0.91
        assert restored.next_agent == "impact"

    def test_human_review_required_has_timeout(self):
        event = HumanReviewRequiredEvent(
            session_id="sess_001",
            timeout_seconds=600,
            timeout_at=datetime(2026, 4, 29, 12, 0, 0),
            summary_for_engineer="建议 OTDR 测试 + 倒换",
            risk_level="medium",
        )
        assert event.timeout_seconds == 600
        assert event.risk_level == "medium"

    def test_human_feedback_received(self):
        event = HumanFeedbackReceivedEvent(
            session_id="sess_001",
            decision="adopted",
            actual_action="执行了 OTDR 测试并更换光纤",
            effectiveness="resolved",
        )
        data = event.model_dump()
        restored = HumanFeedbackReceivedEvent(**data)
        assert restored.decision == "adopted"
        assert restored.effectiveness == "resolved"

    def test_knowledge_closure_payload(self):
        event = KnowledgeClosureRequestedEvent(
            session_id="sess_001",
            root_cause="光纤劣化",
            alarm_names=["LINK_FAIL", "OTU_LOF"],
            suggested_actions=[
                {"step": 1, "action": "OTDR测试", "estimated_time": "15min"},
                {"step": 2, "action": "更换光纤", "estimated_time": "30min"},
            ],
            feedback={"decision": "adopted", "effectiveness": "resolved"},
        )
        assert len(event.suggested_actions) == 2
        assert event.feedback["decision"] == "adopted"

    def test_session_resolved_with_mttr(self):
        event = SessionResolvedEvent(
            session_id="sess_001",
            final_status="resolved",
            mttr_seconds=310,
        )
        assert event.final_status == "resolved"
        assert event.mttr_seconds == 310
