"""诊断 Agent Consumer — 消费 diagnosis_requested 事件"""
import logging
import time
from typing import Optional

from omniops.agents import DiagnosisAgent
from omniops.events.schemas import (
    DiagnosisRequestedEvent,
)
from omniops.memory.persistence import SessionPersistence
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import CognitiveSummary, SessionStatus
from omniops.mq import BaseConsumer
from omniops.router.context_router import AgentMode, ContextRouter

logger = logging.getLogger(__name__)


class DiagnosisConsumer(BaseConsumer):
    """消费 diagnosis_requested 事件，执行诊断后发布下一事件"""

    def __init__(self) -> None:
        super().__init__("omniops.diagnosis")

    async def handle_event(self, event: DiagnosisRequestedEvent) -> None:  # type: ignore[override]
        session_id = event.session_id
        logger.info(f"[DiagnosisConsumer] processing session={session_id}")

        # 加载 session
        store = await get_redis_session_store()
        session = await store.get(session_id)
        if not session:
            logger.error(f"Session {session_id} not found, skipping")
            return

        # 获取锁防止并发
        acquired = await store.acquire_lock(session_id, timeout=60)
        if not acquired:
            logger.warning(f"Could not acquire lock for {session_id}, skipping")
            return

        t0 = time.monotonic()
        error_msg: Optional[str] = None
        cognitive_out: Optional[CognitiveSummary] = None

        try:
            # 执行诊断
            session.status = SessionStatus.DIAGNOSING
            session.current_step = "diagnosing"
            await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)

            agent = DiagnosisAgent()
            cognitive_out = await agent.process(session)

            # 写回 Redis + 持久化 PostgreSQL
            await SessionPersistence.dual_write(
                session_id,
                status=session.status,
                current_step=session.current_step,
                diagnosis_result=session.diagnosis_result,
            )

            # 保存 Agent 对话记录
            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="diagnosis",
                step_order=1,
                cognitive_summary=cognitive_out.model_dump() if cognitive_out else None,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

            # 发布完成事件
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()

            # 路由决定下一步
            router = ContextRouter()
            mode = router.decide_mode(session)

            if mode == AgentMode.SINGLE:
                # 单Agent模式：跳到 planning
                session.current_step = "planning"
                session.status = SessionStatus.PLANNING
                await SessionPersistence.dual_write(session_id, status=session.status, current_step=session.current_step)
                await publisher.publish_planning_requested(session)
            else:
                # 多Agent模式：先 impact
                session.current_step = "diagnosing_done"
                await SessionPersistence.dual_write(session_id, current_step=session.current_step)
                await publisher.publish_impact_requested(session)

            logger.info(
                f"[DiagnosisConsumer] completed session={session_id} "
                f"confidence={session.diagnosis_result.confidence if session.diagnosis_result else 0:.2f}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[DiagnosisConsumer] failed: {e}")
            # 保存失败记录
            SessionPersistence.save_conversation(
                session_id=session_id,
                agent_name="diagnosis",
                step_order=1,
                error_message=error_msg,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        finally:
            await store.release_lock(session_id)
