"""RabbitMQ infrastructure"""
from omniops.mq.connection import close_connection, get_connection  # noqa: F401
from omniops.mq.consumer_base import BaseConsumer  # noqa: F401
from omniops.mq.setup import setup_mq  # noqa: F401
