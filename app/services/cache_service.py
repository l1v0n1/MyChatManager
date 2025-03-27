import json
import asyncio
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic, Type
import redis.asyncio as redis
from loguru import logger
from pydantic import BaseModel
from datetime import timedelta

from app.config.settings import settings

T = TypeVar('T')


class CacheService:
    """Redis-based cache service"""
    
    def __init__(self):
        """Initialize the cache service"""
        self._redis: Optional[redis.Redis] = None
        self._is_connected = False
    
    async def connect(self) -> None:
        """Connect to Redis"""
        if self._is_connected:
            return
            
        try:
            self._redis = redis.from_url(
                settings.redis.url,
                socket_timeout=settings.redis.timeout,
                decode_responses=True
            )
            await self._redis.ping()
            self._is_connected = True
            logger.info(f"Connected to Redis: {settings.redis.url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._is_connected = False
    
    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self._is_connected and self._redis:
            await self._redis.close()
            self._is_connected = False
            logger.info("Disconnected from Redis")
    
    async def get(self, key: str) -> Optional[str]:
        """Get a value from the cache"""
        if not self._is_connected:
            await self.connect()
        
        if not self._is_connected:
            logger.warning("Cannot get from cache: not connected to Redis")
            return None
        
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set a value in the cache"""
        if not self._is_connected:
            await self.connect()
        
        if not self._is_connected:
            logger.warning("Cannot set in cache: not connected to Redis")
            return False
        
        try:
            ttl = ttl or settings.redis.ttl
            return await self._redis.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Error setting in cache: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a value from the cache"""
        if not self._is_connected:
            await self.connect()
        
        if not self._is_connected:
            logger.warning("Cannot delete from cache: not connected to Redis")
            return False
        
        try:
            return bool(await self._redis.delete(key))
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a JSON value from the cache"""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from cache: {e}")
        return None
    
    async def set_json(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set a JSON value in the cache"""
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except Exception as e:
            logger.error(f"Error encoding JSON for cache: {e}")
            return False
    
    async def get_model(self, key: str, model_cls: Type[T]) -> Optional[T]:
        """Get a model instance from the cache"""
        data = await self.get_json(key)
        if data:
            try:
                return model_cls(**data)
            except Exception as e:
                logger.error(f"Error creating model from cache data: {e}")
        return None
    
    async def set_model(self, key: str, model: BaseModel, ttl: Optional[int] = None) -> bool:
        """Set a model instance in the cache"""
        try:
            return await self.set_json(key, model.dict(), ttl)
        except Exception as e:
            logger.error(f"Error serializing model for cache: {e}")
            return False
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching a pattern"""
        if not self._is_connected:
            await self.connect()
        
        if not self._is_connected:
            logger.warning("Cannot get keys from cache: not connected to Redis")
            return []
        
        try:
            return await self._redis.keys(pattern)
        except Exception as e:
            logger.error(f"Error getting keys from cache: {e}")
            return []
    
    async def flush(self) -> bool:
        """Flush the entire cache"""
        if not self._is_connected:
            await self.connect()
        
        if not self._is_connected:
            logger.warning("Cannot flush cache: not connected to Redis")
            return False
        
        try:
            return bool(await self._redis.flushdb())
        except Exception as e:
            logger.error(f"Error flushing cache: {e}")
            return False


# Create singleton instance
cache_service = CacheService()
