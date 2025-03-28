import asyncio
import inspect
from typing import Dict, List, Any, Callable, Awaitable, Set, Optional, Union
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
    
    def json(self) -> str:
        """Compatibility method for both Pydantic v1 and v2"""
        if hasattr(self, 'model_dump_json'):
            return self.model_dump_json()
        return super().json()


class EventManager:
    """Event manager for handling internal events"""
    def __init__(self):
        """Initialize event manager"""
        self.events = {}
        self.connected = False
        self._queue = asyncio.Queue()
        self._running = False
        self._worker_task = None
    
    async def connect(self) -> None:
        """Connect to event system"""
        self.connected = True
        logger.info("Event manager connected")
        
        # Start background task to process events
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())
    
    async def disconnect(self) -> None:
        """Disconnect from event system"""
        self.connected = False
        self._running = False
        
        # Wait for worker to finish if it's running
        if self._worker_task:
            try:
                self._worker_task.cancel()
                await asyncio.wait_for(self._worker_task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            
        logger.info("Event manager disconnected")
    
    async def publish(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Publish an event"""
        if not self.connected:
            logger.warning(f"Event manager not connected, can't publish event: {event_type}")
            return False
        
        # Add metadata to event
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        
        # Add to queue
        await self._queue.put(event)
        
        return True
    
    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Subscribe to an event type"""
        if event_type not in self.events:
            self.events[event_type] = []
        
        self.events[event_type].append(callback)
        logger.debug(f"Subscribed to event: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> bool:
        """Unsubscribe from an event type"""
        if event_type not in self.events:
            return False
        
        if callback in self.events[event_type]:
            self.events[event_type].remove(callback)
            logger.debug(f"Unsubscribed from event: {event_type}")
            return True
        
        return False
    
    async def _process_events(self) -> None:
        """Background task to process events from queue"""
        logger.info("Event processor started")
        
        while self._running:
            try:
                # Get event from queue (with timeout to allow checking _running flag)
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                event_type = event.get("type")
                
                # Check if anyone is subscribed to this event
                if event_type in self.events and self.events[event_type]:
                    # Call all subscribers
                    for callback in self.events[event_type]:
                        try:
                            await callback(event)
                        except Exception as e:
                            logger.error(f"Error in event subscriber for {event_type}: {e}")
                
                # Mark task as done
                self._queue.task_done()
                
            except Exception as e:
                logger.error(f"Error processing event: {e}")
        
        logger.info("Event processor stopped")


# Create a singleton instance
event_manager = EventManager()


def event_listener(event_type: str):
    """Decorator for registering event listeners"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        # Register the function as a listener
        event_manager.subscribe(event_type, func)
        return wrapper
    
    return decorator
