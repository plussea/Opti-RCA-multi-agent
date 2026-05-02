"""影响 Agent Consumer"""
import logging
import time
from typing import Optional

from omniops.agents import ImpactAgent
from omniops.events.schemas import ImpactRequestedEvent
from omniops.memory.persistence import SessionPersistence
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import CognitiveSummary, SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class ImpactConsumer(BaseConsumer):
    def __init__(self) -> None:
        super().__init__("omniops.impact")

    async def handle_event(self, event: ImpactRequestedEvent) -> None:  # type: ignore[override]
        session_id = event.session_id
        logger.info(f"[ImpactConsumer] session={session_id}")

        store = await get_redis_session_store()
        session = await store.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return

        acquired = await store.acquire_lock(session_id, timeout=60)
        if not acquired:
            return

        t0 = time.monotonic()
        error_msg: Optional[str] = None
        cognitive_out: Optional[CognitiveSummary] = None

        try:
            session.status = SessionStatus.PLANNING
            session.current_step = "planning"
            await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)

            agent = ImpactAgent()
            cognitive_out = await agent.process(session)

            await SessionPersistence.dual_write(
                session_id,
                status=session.status,
                current_step=session.current_step,
                impact=session.impact,
            )

            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="impact",
                step_order=1,
                cognitive_summary=cognitive_out.model_dump() if cognitive_out else None,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()
            await publisher.publish_planning_requested(session)

            logger.info(
                f"[ImpactConsumer] session={session_id} "
                f"affected_ne={len(session.impact.affected_ne) if session.impact else 0}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[ImpactConsumer] failed: {e}")
            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="impact",
                step_order=1,
                error_message=error_msg,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        finally:
            await store.release_lock(session_id)
