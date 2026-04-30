"""Base consumer class for all MQ consumers"""
import json
import logging
from abc import abstractmethod
from typing import Any

from omniops.events.schemas import BaseEvent
from omniops.memory.redis_store import get_redis_session_store

logger = logging.getLogger(__name__)


class BaseConsumer:
    """Abstract base for RabbitMQ consumers.

    Subclasses implement `handle_event()` to define behavior.
    """

    def __init__(self, queue_name: str):
        self.queue_name = queue_name
        self._channel: Any = None
        self._queue: Any = None
        self._running = False

    async def start(self) -> None:
        """Start consuming from the queue."""
        from omniops.mq.connection import get_connection
        conn = await get_connection()
        self._channel = await conn.channel()
        await self._channel.set_qos(prefetch_count=1)
        self._queue = await self._channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "omniops.dlq",
                "x-dead-letter-routing-key": "session.*",
            },
        )
        self._running = True
        logger.info(f"Consumer started on queue: {self.queue_name}")

    async def stop(self) -> None:
        """Stop consuming."""
        self._running = False
        if self._channel:
            await self._channel.close()
        logger.info(f"Consumer stopped: {self.queue_name}")

    async def run(self) -> None:
        """Main consume loop."""
        if self._queue is None:
            await self.start()

        async with self._queue.iterator() as queue_iter:  # type: ignore[union-attr]
            async for message in queue_iter:
                if not self._running:
                    break
                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message on {self.queue_name}: {e}")
                    await message.nack(requeue=False)

    async def _process_message(self, message: Any) -> None:
        """Parse and handle a message."""
        try:
            body = json.loads(message.body.decode())
            event_type = body.get("event_type", "unknown")
            session_id = body.get("session_id", "?")

            logger.info(
                f"[{self.queue_name}] received event={event_type} session={session_id}"
            )

            # Deserialize to appropriate event type
            event = self._deserialize(body)
            await self.handle_event(event)
            await message.ack()

        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            await message.nack(requeue=False)

    def _deserialize(self, body: dict) -> BaseEvent:
        """Deserialize a raw dict to the correct event type."""
        from omniops.events import schemas as s

        mapping = {
            "diagnosis_requested": s.DiagnosisRequestedEvent,
            "diagnosis_completed": s.DiagnosisCompletedEvent,
            "impact_requested": s.ImpactRequestedEvent,
            "planning_requested": s.PlanningRequestedEvent,
            "planning_completed": s.PlanningCompletedEvent,
            "verification_requested": s.VerificationRequestedEvent,
            "verification_result": s.VerificationResultEvent,
            "human_review_required": s.HumanReviewRequiredEvent,
            "human_feedback_received": s.HumanFeedbackReceivedEvent,
            "knowledge_closure_requested": s.KnowledgeClosureRequestedEvent,
            "session_resolved": s.SessionResolvedEvent,
        }

        cls = mapping.get(body.get("event_type", ""), BaseEvent)
        return cls(**body)  # type: ignore[no-any-return]

    @abstractmethod
    async def handle_event(self, event: BaseEvent) -> None:
        """Override to define event handling logic."""
        ...

    async def get_session(self, session_id: str) -> Any:
        """Load session from Redis."""
        try:
            store = await get_redis_session_store()
            return await store.get(session_id)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def update_session(self, session_id: str, **updates: Any) -> None:
        """Update session in Redis."""
        try:
            store = await get_redis_session_store()
            await store.update(session_id, **updates)
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
