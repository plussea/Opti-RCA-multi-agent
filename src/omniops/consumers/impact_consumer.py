"""影响 Agent Consumer"""
import logging

from omniops.agents import ImpactAgent
from omniops.events.schemas import ImpactRequestedEvent
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
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

        try:
            session.status = SessionStatus.PLANNING
            session.current_step = "planning"
            await store.update(session_id, status=session.status, current_step=session.current_step)

            agent = ImpactAgent()
            await agent.process(session)

            await store.update(
                session_id,
                status=session.status,
                current_step=session.current_step,
                impact=session.impact,
            )

            # 发布 planning 事件
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()
            await publisher.publish_planning_requested(session)

            logger.info(
                f"[ImpactConsumer] session={session_id} "
                f"affected_ne={len(session.impact.affected_ne) if session.impact else 0}"
            )

        finally:
            await store.release_lock(session_id)
