"""校验 Agent Consumer"""
import logging
import time
from typing import Optional

from omniops.agents import VerificationAgent
from omniops.events.schemas import VerificationRequestedEvent
from omniops.memory.persistence import SessionPersistence
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class VerificationConsumer(BaseConsumer):
    def __init__(self) -> None:
        super().__init__("omniops.verification")

    async def handle_event(self, event: VerificationRequestedEvent) -> None:  # type: ignore[override]
        session_id = event.session_id
        logger.info(f"[VerificationConsumer] session={session_id}")

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

        try:
            session.status = SessionStatus.VERIFYING
            session.current_step = "verifying"
            await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)

            agent = VerificationAgent()
            summary = await agent.process(session)

            await SessionPersistence.dual_write(
                session_id,
                status=session.status,
                current_step=session.current_step,
            )

            await SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="verification",
                step_order=1,
                cognitive_summary=summary.model_dump() if summary else None,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()

            # Check needs_approval: if the plan requires human sign-off, send to HITL
            needs_approval = session.suggestion.needs_approval if session.suggestion else False

            if needs_approval:
                session.current_step = "pending_human"
                session.status = SessionStatus.PENDING_HUMAN
                await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_human_review_required(
                    session_id=session_id,
                    timeout_seconds=600,
                    summary=f"{session.diagnosis_result.root_cause if session.diagnosis_result else 'N/A'} — "
                            f"{len(session.suggestion.suggested_actions) if session.suggestion else 0} 个修复步骤",
                    risk_level=session.suggestion.risk_level if session.suggestion else "low",
                )
            else:
                # All checks passed + no approval needed — auto-complete
                session.current_step = "completed"
                session.status = SessionStatus.COMPLETED
                await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_session_resolved(
                    session_id=session_id,
                    final_status="completed",
                    mttr_seconds=None,
                )

            logger.info(
                f"[VerificationConsumer] session={session_id} "
                f"action={summary.required_action} checks={len(summary.evidence)}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[VerificationConsumer] failed: {e}")
            await SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="verification",
                step_order=1,
                error_message=error_msg,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        finally:
            await store.release_lock(session_id)
