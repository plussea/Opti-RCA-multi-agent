"""Human Review Consumer — 监听人工审核队列，处理超时/反馈"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from omniops.events.schemas import HumanFeedbackReceivedEvent, HumanReviewRequiredEvent
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer

logger = logging.getLogger(__name__)


class HumanReviewConsumer(BaseConsumer):
    """监听 human_review 队列：

    1. 收到 HumanReviewRequiredEvent → 记录到 Redis，设置过期时间
    2. 收到 HumanFeedbackReceivedEvent → 确认反馈，触发知识闭环
    3. 消息 TTL 超时 → 移到 DLQ → 标记 session 为 ESCALATED
    """

    def __init__(self):
        super().__init__("omniops.human_review")
        self._pending: dict = {}  # session_id → timeout_task

    async def handle_event(self, event) -> None:
        from omniops.events.schemas import BaseEvent

        if isinstance(event, HumanReviewRequiredEvent):
            await self._handle_review_required(event)
        elif isinstance(event, HumanFeedbackReceivedEvent):
            await self._handle_feedback_received(event)
        else:
            logger.warning(f"Unexpected event type on human_review: {type(event)}")

    async def _handle_review_required(self, event: HumanReviewRequiredEvent) -> None:
        """启动计时器，超时则升级"""
        session_id = event.session_id
        timeout_secs = event.timeout_seconds

        logger.info(
            f"[HumanReviewConsumer] awaiting human review for {session_id}, "
            f"timeout={timeout_secs}s"
        )

        # 在 Redis 中标记 pending human
        store = await get_redis_session_store()
        await store.update(
            session_id,
            status=SessionStatus.PENDING_HUMAN,
            current_step="pending_human",
        )

        # 启动超时任务
        async def timeout_watcher(sid: str, secs: int):
            await asyncio.sleep(secs)
            await self._handle_timeout(sid, secs)

        task = asyncio.create_task(timeout_watcher(session_id, timeout_secs))
        self._pending[session_id] = task

    async def _handle_feedback_received(self, event: HumanFeedbackReceivedEvent) -> None:
        """工程师提交反馈，取消超时任务，触发知识闭环"""
        session_id = event.session_id
        logger.info(f"[HumanReviewConsumer] feedback received: {session_id} decision={event.decision}")

        # 取消超时任务
        task = self._pending.pop(session_id, None)
        if task:
            task.cancel()

        # 更新 session 状态
        store = await get_redis_session_store()
        if event.decision in ("adopted", "modified"):
            status = SessionStatus.APPROVED
        else:
            status = SessionStatus.REJECTED

        session = await store.get(session_id)
        if session:
            session.human_feedback = {
                "decision": event.decision,
                "actual_action": event.actual_action,
                "effectiveness": event.effectiveness,
                "feedback_at": datetime.utcnow().isoformat(),
            }
            session.status = status
            session.current_step = "resolving"
            await store.update(
                session_id,
                status=status,
                current_step="resolving",
                human_feedback=session.human_feedback,
            )

        # 发布知识闭环事件
        from omniops.events.publisher import get_publisher
        publisher = await get_publisher()
        await publisher.publish_knowledge_closure_requested(
            session_id=session_id,
            root_cause=session.diagnosis_result.root_cause if session and session.diagnosis_result else "",
            alarm_codes=[
                r.alarm_code for r in (session.structured_data if session else [])
                if r.alarm_code
            ],
            suggested_actions=[
                a.model_dump() for a in (session.suggestion.suggested_actions if session and session.suggestion else [])
            ],
            feedback={
                "decision": event.decision,
                "effectiveness": event.effectiveness,
            },
        )

    async def _handle_timeout(self, session_id: str, timeout_secs: int) -> None:
        """人工审核超时 → 升级"""
        logger.warning(f"[HumanReviewConsumer] session {session_id} timed out after {timeout_secs}s")

        try:
            store = await get_redis_session_store()
            await store.update(
                session_id,
                status=SessionStatus.ESCALATED,
                current_step="escalated",
            )

            # 调用升级 webhook（如配置了）
            from omniops.core.config import get_settings
            settings = get_settings()
            webhook_url = settings.hitl_escalation_webhook_url
            if webhook_url:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        webhook_url,
                        json={
                            "session_id": session_id,
                            "event": "human_review_timeout",
                            "timeout_seconds": timeout_secs,
                        },
                    )
                logger.info(f"Escalation webhook sent for {session_id}")

            # 触发知识闭环（超时也是闭环）
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()
            await publisher.publish_session_resolved(
                session_id=session_id,
                final_status="escalated",
                mttr_seconds=timeout_secs,
            )

        except Exception as e:
            logger.error(f"Failed to handle timeout for {session_id}: {e}")
