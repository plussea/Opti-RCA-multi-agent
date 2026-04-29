"""校验 Agent Consumer"""
import logging

from omniops.agents import VerificationAgent
from omniops.events.schemas import VerificationRequestedEvent
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class VerificationConsumer(BaseConsumer):
    def __init__(self):
        super().__init__("omniops.verification")

    async def handle_event(self, event: VerificationRequestedEvent) -> None:
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

        try:
            session.status = SessionStatus.VERIFYING
            session.current_step = "verifying"
            await store.update(session_id, status=session.status, current_step=session.current_step)

            agent = VerificationAgent()
            summary = await agent.process(session)

            await store.update(
                session_id,
                status=session.status,
                current_step=session.current_step,
            )

            # 根据校验结果决定下一步
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()

            if summary.required_action == "pending_human":
                session.current_step = "pending_human"
                session.status = SessionStatus.PENDING_HUMAN
                await store.update(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_human_review_required(
                    session_id=session_id,
                    timeout_seconds=600,
                    summary=f"{session.diagnosis_result.root_cause if session.diagnosis_result else 'N/A'} — "
                            f"{len(session.suggestion.suggested_actions) if session.suggestion else 0} 个修复步骤",
                    risk_level=session.suggestion.risk_level if session.suggestion else "low",
                )
            else:
                session.current_step = "failed"
                session.status = SessionStatus.FAILED
                await store.update(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_session_resolved(
                    session_id=session_id,
                    final_status="failed",
                    mttr_seconds=None,
                )

            logger.info(
                f"[VerificationConsumer] session={session_id} "
                f"action={summary.required_action} checks={len(summary.evidence)}"
            )

        finally:
            await store.release_lock(session_id)
