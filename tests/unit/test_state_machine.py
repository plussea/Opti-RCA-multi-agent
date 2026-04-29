"""Tests for session state machine transitions"""
import pytest

from omniops.models import Session, SessionStatus
from omniops.router.context_router import AgentMode, ContextRouter


class TestContextRouter:
    def setup_method(self):
        self.router = ContextRouter()

    def _make_session(self, current_step: str, status: SessionStatus) -> Session:
        return Session(
            session_id="sess_test",
            input_type="csv",
            structured_data=[],
            status=status,
            current_step=current_step,
        )

    # ── route_after_agent tests ────────────────────────────────────────────────

    def test_perception_completed_routes_to_diagnosis(self):
        s = self._make_session("init", SessionStatus.ANALYZING)
        next_agent = self.router.route_after_agent(s, "perception")
        assert next_agent == "diagnosis"
        assert s.current_step == "perceived"
        assert s.status == SessionStatus.PERCEIVED

    def test_diagnosis_completed_multi_routes_to_impact(self):
        s = self._make_session("perceived", SessionStatus.PERCEIVED)
        s.structured_data = [None] * 6  # ≥5 → MULTI mode
        next_agent = self.router.route_after_agent(s, "diagnosis")
        assert next_agent == "impact"
        assert s.current_step == "diagnosing"

    def test_diagnosis_completed_single_routes_to_planning(self):
        s = self._make_session("perceived", SessionStatus.PERCEIVED)
        s.structured_data = [None] * 3  # <5 → SINGLE mode
        next_agent = self.router.route_after_agent(s, "diagnosis")
        assert next_agent == "planning"

    def test_impact_completed_routes_to_planning(self):
        s = self._make_session("diagnosing", SessionStatus.DIAGNOSING)
        next_agent = self.router.route_after_agent(s, "impact")
        assert next_agent == "planning"
        assert s.current_step == "planning"

    def test_planning_completed_routes_to_verification(self):
        s = self._make_session("planning", SessionStatus.PLANNING)
        next_agent = self.router.route_after_agent(s, "planning")
        assert next_agent == "verification"
        assert s.current_step == "verifying"

    def test_verification_with_human_required(self):
        from omniops.models import Suggestion, SuggestionAction

        s = self._make_session("verifying", SessionStatus.VERIFYING)
        s.suggestion = Suggestion(
            root_cause="光纤劣化",
            suggested_actions=[
                SuggestionAction(step=1, action="更换光纤", estimated_time="30min")
            ],
            risk_level="high",
            needs_approval=True,
        )
        next_agent = self.router.route_after_agent(s, "verification")
        assert next_agent == "human_review"
        assert s.current_step == "pending_human"
        assert s.status == SessionStatus.PENDING_HUMAN

    def test_verification_no_human_auto_complete(self):
        from omniops.models import Suggestion, SuggestionAction

        s = self._make_session("verifying", SessionStatus.VERIFYING)
        s.suggestion = Suggestion(
            root_cause="光纤劣化",
            suggested_actions=[
                SuggestionAction(step=1, action="清洁端面", estimated_time="5min")
            ],
            risk_level="low",
            needs_approval=False,
        )
        next_agent = self.router.route_after_agent(s, "verification")
        assert next_agent == "closure"
        assert s.status == SessionStatus.COMPLETED

    def test_human_review_routes_to_closure(self):
        s = self._make_session("pending_human", SessionStatus.PENDING_HUMAN)
        s.human_feedback = {"decision": "adopted", "actual_action": "已执行"}
        next_agent = self.router.route_after_agent(s, "human_review")
        assert next_agent == "closure"
        assert s.status == SessionStatus.APPROVED

    # ── decide_mode tests ─────────────────────────────────────────────────────

    def test_single_mode_below_threshold(self):
        from omniops.models import AlarmRecord

        s = self._make_session("init", SessionStatus.ANALYZING)
        s.structured_data = [
            AlarmRecord(ne_name="NE-01", alarm_code="LINK_FAIL")
            for _ in range(3)
        ]
        mode = self.router.decide_mode(s)
        assert mode == AgentMode.SINGLE

    def test_multi_mode_above_threshold(self):
        from omniops.models import AlarmRecord

        s = self._make_session("init", SessionStatus.ANALYZING)
        s.structured_data = [
            AlarmRecord(ne_name=f"NE-{i:02d}", alarm_code="LINK_FAIL")
            for i in range(6)
        ]
        mode = self.router.decide_mode(s)
        assert mode == AgentMode.MULTI

    # ── current_step tracking ───────────────────────────────────────────────────

    def test_current_step_evolves_correctly(self):
        from omniops.models import AlarmRecord

        s = self._make_session("init", SessionStatus.ANALYZING)
        s.structured_data = [
            AlarmRecord(ne_name=f"NE-{i:02d}", alarm_code="LINK_FAIL")
            for i in range(6)
        ]

        self.router.route_after_agent(s, "perception")
        assert s.current_step == "perceived"

        self.router.route_after_agent(s, "diagnosis")
        assert s.current_step == "diagnosing"

        self.router.route_after_agent(s, "impact")
        assert s.current_step == "planning"
