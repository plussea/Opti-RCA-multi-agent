"""知识闭环 Consumer — 反馈后写入向量库"""
import logging
from datetime import datetime

from omniops.events.schemas import KnowledgeClosureRequestedEvent
from omniops.memory.persistence import SessionPersistence
from omniops.memory.redis_store import get_redis_session_store
from omniops.models import SessionStatus
from omniops.mq import BaseConsumer
from omniops.rag import ingest_knowledge

logger = logging.getLogger(__name__)


class ClosureConsumer(BaseConsumer):
    def __init__(self) -> None:
        super().__init__("omniops.closure")

    async def handle_event(self, event: KnowledgeClosureRequestedEvent) -> None:  # type: ignore[override]
        session_id = event.session_id
        logger.info(f"[ClosureConsumer] processing session={session_id}")

        try:
            # 读取 session（如尚未在事件中）
            store = await get_redis_session_store()
            session = await store.get(session_id)

            # 知识沉淀：采纳/修改 → 写向量库
            feedback = event.feedback or {}
            if feedback.get("decision") in ("adopted", "modified"):
                alarm_names = event.alarm_names
                if not alarm_names and session:
                    alarm_names = [
                        r.alarm_name for r in session.structured_data
                        if r.alarm_name
                    ]

                try:
                    doc_id = await ingest_knowledge(
                        root_cause=event.root_cause,
                        alarm_codes=alarm_names,
                        suggested_actions=event.suggested_actions,
                        source_session=session_id,
                    )
                    logger.info(f"[ClosureConsumer] knowledge entry written: {doc_id}")
                except Exception as ke:
                    logger.warning(f"[ClosureConsumer] knowledge ingest failed: {ke}")

            # 计算 MTTR
            mttr_seconds = None
            if session:
                mttr_seconds = int((datetime.utcnow() - session.created_at).total_seconds())

            # 更新 session 为终态
            await store.update(
                session_id,
                status=SessionStatus.RESOLVED,
                current_step="resolved",
            )
            await SessionPersistence.dual_write(
                session_id,
                status=SessionStatus.RESOLVED,
                current_step="resolved",
            )

            # 发布终态事件
            from omniops.events.publisher import get_publisher
            publisher = await get_publisher()
            await publisher.publish_session_resolved(
                session_id=session_id,
                final_status="resolved",
                mttr_seconds=mttr_seconds,
            )

            logger.info(
                f"[ClosureConsumer] session={session_id} resolved, "
                f"decision={feedback.get('decision')}, mttr={mttr_seconds}s"
            )

        except Exception as e:
            logger.error(f"[ClosureConsumer] failed for {session_id}: {e}")
