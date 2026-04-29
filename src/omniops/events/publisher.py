"""Event publisher for OmniOps event bus.

This module publishes events to RabbitMQ. In Phase 1-3 (no RabbitMQ running),
it stubs to structured log output so the pipeline can be traced end-to-end.
When RabbitMQ is available (Phase 4+), this upgrades to real aio-pika publish.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from omniops.events.schemas import BaseEvent

logger = logging.getLogger(__name__)

# Routing key mapping: event_type → queue/routing_key
_ROUTING_KEYS = {
    "diagnosis_requested": "session.{session_id}.diagnosis_requested",
    "diagnosis_completed": "session.{session_id}.diagnosis_completed",
    "impact_requested": "session.{session_id}.impact_requested",
    "planning_requested": "session.{session_id}.planning_requested",
    "planning_completed": "session.{session_id}.planning_completed",
    "verification_requested": "session.{session_id}.verification_requested",
    "verification_result": "session.{session_id}.verification_result",
    "human_review_required": "session.{session_id}.human_review_required",
    "human_feedback_received": "session.{session_id}.human_feedback_received",
    "knowledge_closure_requested": "session.{session_id}.knowledge_closure_requested",
    "session_resolved": "session.{session_id}.session_resolved",
}


class OmniOpsPublisher:
    """Event publisher.

    Uses real RabbitMQ if connection is available (Phase 4+),
    otherwise falls back to structured logging.
    """

    def __init__(self):
        self._connection = None
        self._channel = None
        self._real_mode = False

    async def connect(self) -> None:
        """Try to connect to RabbitMQ; silently fall back to stub mode."""
        try:
            from omniops.mq.connection import get_connection
            conn = await get_connection()
            self._channel = await conn.channel()
            await self._channel.set_qos(prefetch_count=1)
            self._real_mode = True
            logger.info("OmniOpsPublisher: connected to RabbitMQ (real mode)")
        except Exception as e:
            logger.warning(f"OmniOpsPublisher: RabbitMQ not available, using stub mode. {e}")
            self._real_mode = False

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to the bus."""
        routing_key = _ROUTING_KEYS.get(
            event.event_type,
            f"session.{event.session_id}.{event.event_type}",
        )

        if self._real_mode and self._channel:
            await self._publish_real(event, routing_key)
        else:
            self._publish_stub(event, routing_key)

    async def _publish_real(self, event: BaseEvent, routing_key: str) -> None:
        import aio_pika
        body = event.model_dump_json().encode()
        msg = aio_pika.Message(
            body=body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        exchange = await self._channel.get_exchange("omniops.events")
        await exchange.publish(msg, routing_key=routing_key)

    def _publish_stub(self, event: BaseEvent, routing_key: str) -> None:
        data = json.loads(event.model_dump_json())
        logger.info(
            "[EVENT_STUB] routing_key=%s event_type=%s session_id=%s payload=%s",
            routing_key,
            event.event_type,
            event.session_id,
            json.dumps(data, ensure_ascii=False),
        )

    # ── Convenience publish methods ──────────────────────────────────────────

    async def publish_diagnosis_requested(self, session) -> None:
        from omniops.events.schemas import DiagnosisRequestedEvent
        alarm_codes = {r.alarm_code for r in session.structured_data if r.alarm_code}
        event = DiagnosisRequestedEvent(
            session_id=session.session_id,
            alarm_codes=alarm_codes,
            structured_data=[r.model_dump() for r in session.structured_data],
            priority=2,
        )
        await self.publish(event)

    async def publish_diagnosis_completed(
        self,
        session_id: str,
        confidence: float,
        root_cause: str,
        uncertainty: Optional[str],
        next_agent: str,
    ) -> None:
        from omniops.events.schemas import DiagnosisCompletedEvent
        event = DiagnosisCompletedEvent(
            session_id=session_id,
            confidence=confidence,
            root_cause_summary=root_cause,
            uncertainty=uncertainty,
            next_agent=next_agent,
        )
        await self.publish(event)

    async def publish_impact_requested(self, session) -> None:
        from omniops.events.schemas import ImpactRequestedEvent
        event = ImpactRequestedEvent(
            session_id=session.session_id,
            root_cause=getattr(session, "diagnosis_result", None) and session.diagnosis_result.root_cause or "",
            confidence=getattr(session, "diagnosis_result", None) and session.diagnosis_result.confidence or 0.0,
        )
        await self.publish(event)

    async def publish_planning_requested(self, session) -> None:
        from omniops.events.schemas import PlanningRequestedEvent
        diag = getattr(session, "diagnosis_result", None)
        imp = getattr(session, "impact", None)
        event = PlanningRequestedEvent(
            session_id=session.session_id,
            root_cause=diag.root_cause if diag else "",
            confidence=diag.confidence if diag else 0.0,
            impact_summary=imp.model_dump() if imp else None,
        )
        await self.publish(event)

    async def publish_verification_requested(self, session) -> None:
        from omniops.events.schemas import VerificationRequestedEvent
        event = VerificationRequestedEvent(
            session_id=session.session_id,
            root_cause=getattr(session, "diagnosis_result", None) and session.diagnosis_result.root_cause or "",
            suggestion_summary=getattr(session, "suggestion", None) and session.suggestion.model_dump() or None,
            diagnosis_summary=getattr(session, "diagnosis_result", None) and session.diagnosis_result.model_dump() or None,
        )
        await self.publish(event)

    async def publish_human_review_required(
        self,
        session_id: str,
        timeout_seconds: int,
        summary: str,
        risk_level: str,
    ) -> None:
        from omniops.events.schemas import HumanReviewRequiredEvent
        event = HumanReviewRequiredEvent(
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            timeout_at=datetime.utcnow().replace(microsecond=0).__add__(
                __import__("datetime").timedelta(seconds=timeout_seconds)
            ),
            summary_for_engineer=summary,
            risk_level=risk_level,
        )
        await self.publish(event)

    async def publish_human_feedback_received(
        self,
        session_id: str,
        decision: str,
        actual_action: str,
        effectiveness: str,
    ) -> None:
        from omniops.events.schemas import HumanFeedbackReceivedEvent
        event = HumanFeedbackReceivedEvent(
            session_id=session_id,
            decision=decision,
            actual_action=actual_action,
            effectiveness=effectiveness,
        )
        await self.publish(event)

    async def publish_knowledge_closure_requested(
        self,
        session_id: str,
        root_cause: str,
        alarm_codes: list,
        suggested_actions: list,
        feedback: Optional[dict],
    ) -> None:
        from omniops.events.schemas import KnowledgeClosureRequestedEvent
        event = KnowledgeClosureRequestedEvent(
            session_id=session_id,
            root_cause=root_cause,
            alarm_codes=alarm_codes,
            suggested_actions=suggested_actions,
            feedback=feedback,
        )
        await self.publish(event)

    async def publish_session_resolved(
        self,
        session_id: str,
        final_status: str,
        mttr_seconds: Optional[int],
    ) -> None:
        from omniops.events.schemas import SessionResolvedEvent
        event = SessionResolvedEvent(
            session_id=session_id,
            final_status=final_status,
            mttr_seconds=mttr_seconds,
        )
        await self.publish(event)


_publisher: Optional[OmniOpsPublisher] = None


async def get_publisher() -> OmniOpsPublisher:
    """Get or create the singleton publisher."""
    global _publisher
    if _publisher is None:
        _publisher = OmniOpsPublisher()
        await _publisher.connect()
    return _publisher


async def close_publisher() -> None:
    global _publisher
    if _publisher is not None:
        await _publisher.close()
        _publisher = None
