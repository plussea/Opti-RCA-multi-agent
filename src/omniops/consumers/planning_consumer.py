"""方案 Agent Consumer"""
import logging

from omniops.agents import ImpactAgent, PlanningAgent
from omniops.events.schemas import PlanningRequestedEvent
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class PlanningConsumer(BaseConsumer):
    def __init__(self):
        super().__init__("omniops.planning")

    async def handle_event(self, event: PlanningRequestedEvent) -> None:
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

        try:
            # 先执行 impact（如尚未执行）
            if not session.impact:
                impact_agent = ImpactAgent()
                await impact_agent.process(session)
                await store.update(session_id, impact=session.impact)

            # 执行规划
            session.status = SessionStatus.PLANNING
            session.current_step = "planning"
            await store.update(session_id, status=session.status, current_step=session.current_step)

            plan_agent = PlanningAgent()
            await plan_agent.process(session)

            await store.update(
                session_id,
                status=session.status,
                current_step=session.current_step,
                suggestion=session.suggestion,
            )

            # 发布校验事件
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()

            # 路由决定下一步
            suggestion = session.suggestion
            if suggestion and suggestion.needs_approval:
                session.current_step = "pending_human"
                session.status = SessionStatus.PENDING_HUMAN
                await store.update(session_id, status=session.status, current_step=session.current_step)
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
                await store.update(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_verification_requested(session)

            logger.info(f"[PlanningConsumer] completed session={session_id}")

        finally:
            await store.release_lock(session_id)
