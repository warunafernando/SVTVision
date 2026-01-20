"""Message bus for SVTVision."""

from typing import Callable, Dict, List, Any
from collections import defaultdict
from ..services.logging_service import LoggingService


class MessageBus:
    """Simple message bus for pub/sub communication."""
    
    def __init__(self, logger: LoggingService):
        self.logger = logger
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
    
    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic."""
        self.subscribers[topic].append(callback)
        self.logger.debug(f"Subscribed to topic: {topic}")
    
    def unsubscribe(self, topic: str, callback: Callable):
        """Unsubscribe from a topic."""
        if callback in self.subscribers[topic]:
            self.subscribers[topic].remove(callback)
            self.logger.debug(f"Unsubscribed from topic: {topic}")
    
    def publish(self, topic: str, message: Any):
        """Publish message to a topic."""
        callbacks = self.subscribers.get(topic, [])
        self.logger.debug(f"Publishing to topic: {topic} ({len(callbacks)} subscribers)")
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self.logger.error(f"Error in callback for topic {topic}: {e}")
