"""RabbitMQ connection management"""
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import aio_pika

logger = logging.getLogger(__name__)

_connection: Optional[Any] = None


async def get_connection() -> Any:
    """Get or create the singleton RabbitMQ connection.

    Uses connect_robust for automatic reconnection.
    """
    global _connection
    if _connection is None or _connection.is_closed:
        from omniops.core.config import get_settings
        settings = get_settings()
        try:
            import aio_pika
            _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            logger.info(f"RabbitMQ connected: {settings.rabbitmq_url}")
        except Exception as e:
            logger.error(f"RabbitMQ connection failed: {e}")
            raise
    return _connection


async def close_connection() -> None:
    """Close the RabbitMQ connection."""
    global _connection
    if _connection and not _connection.is_closed:
        await _connection.close()
        _connection = None
        logger.info("RabbitMQ connection closed")
