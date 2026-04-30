"""RabbitMQ exchange and queue setup (called once at startup)"""
import logging

logger = logging.getLogger(__name__)

DLQ_ARGS = {
    "x-dead-letter-exchange": "omniops.dlq",
    "x-dead-letter-routing-key": "session.*",
}


async def setup_mq() -> None:
    """Declare all exchanges, queues, and bindings.

    Call once during FastAPI lifespan startup.
    """
    try:
        from omniops.mq.connection import get_connection
        conn = await get_connection()
        channel = await conn.channel()

        # ── Exchanges ───────────────────────────────────────────────────────────
        await channel.declare_exchange("omniops.events", type="topic", durable=True)
        await channel.declare_exchange("omniops.dlq", type="direct", durable=True)
        await channel.declare_exchange("omniops.hitl", type="topic", durable=True)

        # ── Queues (all with DLX for consistent dead-letter handling) ─────────
        queue_bindings = [
            ("omniops.diagnosis", "session.*.diagnosis_requested"),
            ("omniops.impact", "session.*.impact_requested"),
            ("omniops.planning", "session.*.planning_requested"),
            ("omniops.verification", "session.*.verification_requested"),
            ("omniops.closure", "session.*.knowledge_closure_requested"),
            ("omniops.session_resolved", "session.*.session_resolved"),
            ("omniops.human_review", "session.*.human_review_required"),
            ("omniops.human_review", "session.*.human_feedback_received"),
        ]

        events_exchange = await channel.get_exchange("omniops.events")
        hitl_exchange = await channel.get_exchange("omniops.hitl")
        dlq_exchange = await channel.get_exchange("omniops.dlq")

        # Collect unique queues and declare with DLX
        seen: set = set()
        for queue_name, routing_pattern in queue_bindings:
            if queue_name not in seen:
                seen.add(queue_name)
                q = await channel.declare_queue(
                    queue_name,
                    durable=True,
                    arguments=DLQ_ARGS,
                )
                # Bind to appropriate exchange
                if queue_name == "omniops.human_review":
                    await q.bind(hitl_exchange, routing_key=routing_pattern)
                else:
                    await q.bind(events_exchange, routing_key=routing_pattern)
                logger.info(f"Queue declared and bound: {queue_name}")

        # DLQ binding
        dlq = await channel.declare_queue("omniops.dlq", durable=True)
        await dlq.bind(dlq_exchange, routing_key="session.*")
        logger.info("RabbitMQ setup complete: all exchanges and queues declared")

    except Exception as e:
        logger.warning(f"RabbitMQ setup failed (will retry on connect): {e}")
