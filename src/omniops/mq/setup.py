"""RabbitMQ exchange and queue setup (called once at startup)"""
import logging

logger = logging.getLogger(__name__)


async def setup_mq() -> None:
    """Declare all exchanges, queues, and bindings.

    Call once during FastAPI lifespan startup.
    """
    try:
        from omniops.mq.connection import get_connection
        conn = await get_connection()
        channel = await conn.channel()

        # ── Events exchange (topic) ─────────────────────────────────────────
        events_exchange = await channel.declare_exchange(
            "omniops.events",
            exchange_type="topic",
            durable=True,
        )

        # Queues bound to events exchange
        queues = [
            ("omniops.diagnosis", "session.*.diagnosis_requested"),
            ("omniops.impact", "session.*.impact_requested"),
            ("omniops.planning", "session.*.planning_requested"),
            ("omniops.verification", "session.*.verification_requested"),
            ("omniops.closure", "session.*.knowledge_closure_requested"),
            ("omniops.session_resolved", "session.*.session_resolved"),
        ]
        for queue_name, routing_pattern in queues:
            q = await channel.declare_queue(queue_name, durable=True)
            await q.bind(events_exchange, routing_key=routing_pattern)
            logger.info(f"Queue declared and bound: {queue_name} -> {routing_pattern}")

        # ── Human review exchange + queue (with DLQ) ─────────────────────────
        dlq_exchange = await channel.declare_exchange(
            "omniops.dlq",
            exchange_type="direct",
            durable=True,
        )
        dlq = await channel.declare_queue("omniops.dlq", durable=True)
        await dlq.bind(dlq_exchange, routing_key="session.*")

        hitl_exchange = await channel.declare_exchange(
            "omniops.hitl",
            exchange_type="topic",
            durable=True,
        )
        hr_queue = await channel.declare_queue(
            "omniops.human_review",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "omniops.dlq",
                "x-dead-letter-routing-key": "session.*",
            },
        )
        await hr_queue.bind(hitl_exchange, routing_key="session.*.human_review_required")
        await hr_queue.bind(hitl_exchange, routing_key="session.*.human_feedback_received")
        logger.info("Human review queue with DLQ declared")

        logger.info("RabbitMQ setup complete: all exchanges and queues declared")

    except Exception as e:
        logger.warning(f"RabbitMQ setup failed (will retry on connect): {e}")
