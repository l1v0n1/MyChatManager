import asyncio
import inspect
from typing import Dict, List, Any, Callable, Awaitable, Set, Optional
from loguru import logger
import pika
import json
import uuid
from datetime import datetime
from pydantic import BaseModel
from functools import wraps

from app.config.settings import settings


class Event(BaseModel):
    """Event data model"""
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = datetime.now()
    event_id: str = str(uuid.uuid4())


class EventManager:
    """Event manager using observer pattern"""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable[[Event], Awaitable[None]]]] = {}
        self._connection = None
        self._channel = None
        self._queue_name = settings.rabbitmq.queue_name
        self._exchange_name = settings.rabbitmq.exchange_name
        self._is_connected = False
    
    async def connect_rabbitmq(self) -> None:
        """Connect to RabbitMQ"""
        if self._is_connected:
            return
            
        try:
            # Create connection parameters
            connection_params = pika.URLParameters(settings.rabbitmq.url)
            
            # Create connection (using blocking connection for simplicity)
            self._connection = pika.BlockingConnection(connection_params)
            self._channel = self._connection.channel()
            
            # Declare exchange
            self._channel.exchange_declare(
                exchange=self._exchange_name,
                exchange_type='topic',
                durable=True
            )
            
            # Declare queue
            self._channel.queue_declare(
                queue=self._queue_name,
                durable=True
            )
            
            # Bind queue to exchange
            self._channel.queue_bind(
                queue=self._queue_name,
                exchange=self._exchange_name,
                routing_key='#'  # All routing keys
            )
            
            self._is_connected = True
            logger.info(f"Connected to RabbitMQ: {settings.rabbitmq.url}")
        
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._is_connected = False
    
    def register(self, event_type: str, callback: Callable[[Event], Awaitable[None]]) -> None:
        """Register an event listener"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        
        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)
            logger.debug(f"Registered listener for event '{event_type}': {callback.__name__}")
    
    def unregister(self, event_type: str, callback: Callable[[Event], Awaitable[None]]) -> None:
        """Unregister an event listener"""
        if event_type in self._listeners and callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)
            logger.debug(f"Unregistered listener for event '{event_type}': {callback.__name__}")
    
    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event"""
        event = Event(event_type=event_type, data=data)
        
        # Log the event
        logger.debug(f"Publishing event: {event_type} ({event.event_id})")
        
        # Process locally
        tasks = []
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                task = asyncio.create_task(self._execute_callback(callback, event))
                tasks.append(task)
        
        # Also send to RabbitMQ if connected
        if self._is_connected:
            try:
                self._channel.basic_publish(
                    exchange=self._exchange_name,
                    routing_key=event_type,
                    body=event.json(),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Make message persistent
                        content_type='application/json'
                    )
                )
            except Exception as e:
                logger.error(f"Failed to publish event to RabbitMQ: {e}")
        
        if tasks:
            await asyncio.gather(*tasks)
    
    async def _execute_callback(self, callback: Callable[[Event], Awaitable[None]], event: Event) -> None:
        """Execute callback safely"""
        try:
            await callback(event)
        except Exception as e:
            logger.error(f"Error in event listener {callback.__name__} for event {event.event_type}: {e}")
    
    async def start_consuming(self) -> None:
        """Start consuming messages from RabbitMQ"""
        if not self._is_connected:
            await self.connect_rabbitmq()
        
        if not self._is_connected:
            logger.error("Cannot start consuming: not connected to RabbitMQ")
            return
        
        try:
            # Set up basic consume with callback
            self._channel.basic_consume(
                queue=self._queue_name,
                on_message_callback=self._process_message,
                auto_ack=False
            )
            
            logger.info(f"Started consuming from queue: {self._queue_name}")
            
            # Start consuming (blocking call)
            self._channel.start_consuming()
        
        except Exception as e:
            logger.error(f"Error in RabbitMQ consumer: {e}")
    
    def _process_message(self, ch, method, properties, body) -> None:
        """Process message from RabbitMQ"""
        try:
            # Parse event
            event_data = json.loads(body)
            event = Event(**event_data)
            
            # Create asyncio task for processing
            asyncio.create_task(self._process_event(event))
            
            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error processing message from RabbitMQ: {e}")
            # Negative acknowledge on error
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    async def _process_event(self, event: Event) -> None:
        """Process event from RabbitMQ"""
        logger.debug(f"Processing event from queue: {event.event_type} ({event.event_id})")
        
        if event.event_type in self._listeners:
            tasks = []
            for callback in self._listeners[event.event_type]:
                task = asyncio.create_task(self._execute_callback(callback, event))
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks)


# Create a singleton instance
event_manager = EventManager()


def event_listener(event_type: str):
    """Decorator for registering event listeners"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        # Register the function as a listener
        event_manager.register(event_type, func)
        return wrapper
    
    return decorator
