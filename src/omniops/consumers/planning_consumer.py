"""方案 Agent Consumer"""
import logging
import time
from typing import Optional

from omniops.agents import ImpactAgent, PlanningAgent
from omniops.events.schemas import PlanningRequestedEvent
from omniops.memory.persistence import SessionPersistence
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class PlanningConsumer(BaseConsumer):
    def __init__(self) -> None:
        super().__init__("omniops.planning")

    async def handle_event(self, event: PlanningRequestedEvent) -> None:  # type: ignore[override]
        session_id = event.session_id
        logger.info(f"[PlanningConsumer] session={session_id}")

        store = await get_redis_session_store()
        session = await store.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return

        acquired = await store.acquire_lock(session_id, timeout=60)
        if not acquired:
            logger.warning(f"Lock unavailable for {session_id}")
            return

        t0 = time.monotonic()
        error_msg: Optional[str] = None

        try:
            # 先执行 impact（如尚未执行）
            if not session.impact:
                impact_agent = ImpactAgent()
                await impact_agent.process(session)
                SessionPersistence.dual_write(session_id, impact=session.impact)

            # 执行规划
            session.status = SessionStatus.PLANNING
            session.current_step = "planning"
            SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)

            plan_agent = PlanningAgent()
            plan_out = await plan_agent.process(session)

            SessionPersistence.dual_write(
                session_id,
                status=session.status,
                current_step=session.current_step,
                suggestion=session.suggestion,
            )

            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="planning",
                step_order=1,
                cognitive_summary=plan_out.model_dump() if plan_out else None,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()

            suggestion = session.suggestion
            if suggestion and suggestion.needs_approval:
                session.current_step = "pending_human"
                session.status = SessionStatus.PENDING_HUMAN
                SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_human_review_required(
                    session_id=session_id,
                    timeout_seconds=600,
                    summary=f"{session.diagnosis_result.root_cause if session.diagnosis_result else 'N/A'} — "
                            f"{len(suggestion.suggested_actions)} 个修复步骤，"
                            f"风险等级 {suggestion.risk_level}",
                    risk_level=suggestion.risk_level,
                )
            else:
                session.current_step = "verifying"
                session.status = SessionStatus.VERIFYING
                SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_verification_requested(session)

            logger.info(f"[PlanningConsumer] completed session={session_id}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[PlanningConsumer] failed: {e}")
            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="planning",
                step_order=1,
                error_message=error_msg,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        finally:
            await store.release_lock(session_id)
