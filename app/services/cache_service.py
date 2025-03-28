import json
import asyncio
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic, Type
import redis.asyncio as redis
from loguru import logger
from pydantic import BaseModel
from datetime import timedelta, datetime

from app.config.settings import settings

T = TypeVar('T')


class DummyCache:
    """In-memory cache for when Redis is not available"""
    def __init__(self):
        self.cache = {}
        self.ttls = {}
    
    async def ping(self):
        return True
    
    async def get(self, key):
        # Check if key exists and hasn't expired
        now = asyncio.get_event_loop().time()
        if key in self.cache and (key not in self.ttls or self.ttls[key] > now):
            return self.cache[key]
        # Remove expired keys
        if key in self.ttls and self.ttls[key] <= now:
            del self.cache[key]
            del self.ttls[key]
        return None
    
    async def set(self, key, value, ex=None):
        self.cache[key] = value
        if ex:
            self.ttls[key] = asyncio.get_event_loop().time() + ex
        return True
    
    async def delete(self, key):
        if key in self.cache:
            del self.cache[key]
            if key in self.ttls:
                del self.ttls[key]
            return 1
        return 0
    
    async def keys(self, pattern):
        import fnmatch
        return [k for k in self.cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    async def flushdb(self):
        self.cache.clear()
        self.ttls.clear()
        return True
    
    async def close(self):
        pass


class CacheService:
    """Service for caching data"""
    
    def __init__(self):
        """Initialize cache service"""
        self.connected = False
        self.client = None
        self.in_memory_cache = {}
        self.in_memory_ttl = {}
    
    async def connect(self) -> bool:
        """Connect to Redis if configured, otherwise use in-memory cache"""
        if settings.redis.REDIS_URL:
            try:
                # Connect to Redis
                self.client = redis.from_url(
                    settings.redis.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                
                # Test connection
                await self.client.ping()
                
                self.connected = True
                logger.info(f"Connected to Redis: {settings.redis.REDIS_URL}")
                return True
                
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                logger.warning("Using in-memory cache instead")
                self.client = None
        
        # Use in-memory if Redis not available or connection failed
        if not self.connected:
            logger.info("Using in-memory cache")
            self.in_memory_cache = {}
            self.in_memory_ttl = {}
            self.connected = True
        
        return self.connected
    
    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
            self.client = None
        
        self.connected = False
        logger.info("Disconnected from cache")
    
    async def get(self, key: str) -> Any:
        """Get a value from cache"""
        if not self.connected:
            return None
        
        # Get from Redis
        if self.client:
            try:
                value = await self.client.get(key)
                if value is None:
                    return None
                
                try:
                    # Try to parse as JSON
                    return json.loads(value)
                except json.JSONDecodeError:
                    # Return as string if not JSON
                    return value
                    
            except Exception as e:
                logger.error(f"Error getting key '{key}' from Redis: {e}")
                return None
        
        # Get from in-memory cache
        if key in self.in_memory_cache:
            # Check if expired
            if key in self.in_memory_ttl and self.in_memory_ttl[key] < datetime.now():
                # Expired - remove and return None
                del self.in_memory_cache[key]
                del self.in_memory_ttl[key]
                return None
            
            return self.in_memory_cache[key]
        
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in cache
        
        Args:
            key: Cache key
            value: Value to store (will be JSON serialized)
            ttl: Time-to-live in seconds
        """
        if not self.connected:
            await self.connect()
        
        # Convert to JSON string for storage if not a string already
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            value_str = json.dumps(value)
        else:
            value_str = str(value) if value is not None else None
        
        # Store in Redis
        if self.client:
            try:
                if ttl:
                    await self.client.setex(key, ttl, value_str)
                else:
                    await self.client.set(key, value_str)
                return True
                
            except Exception as e:
                logger.error(f"Error setting key '{key}' in Redis: {e}")
                return False
        
        # Store in in-memory cache
        self.in_memory_cache[key] = value
        
        # Set expiration
        if ttl:
            self.in_memory_ttl[key] = datetime.now() + timedelta(seconds=ttl)
        elif key in self.in_memory_ttl:
            # Remove TTL if exists but not provided
            del self.in_memory_ttl[key]
        
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        if not self.connected:
            return False
        
        # Delete from Redis
        if self.client:
            try:
                return await self.client.delete(key) > 0
                
            except Exception as e:
                logger.error(f"Error deleting key '{key}' from Redis: {e}")
                return False
        
        # Delete from in-memory cache
        if key in self.in_memory_cache:
            del self.in_memory_cache[key]
            if key in self.in_memory_ttl:
                del self.in_memory_ttl[key]
            return True
        
        return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache"""
        if not self.connected:
            return False
        
        # Check in Redis
        if self.client:
            try:
                return await self.client.exists(key) > 0
                
            except Exception as e:
                logger.error(f"Error checking key '{key}' in Redis: {e}")
                return False
        
        # Check in in-memory cache
        return key in self.in_memory_cache and (
            key not in self.in_memory_ttl or
            self.in_memory_ttl[key] >= datetime.now()
        )
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for a key in seconds"""
        if not self.connected:
            return None
        
        # Get from Redis
        if self.client:
            try:
                ttl = await self.client.ttl(key)
                return ttl if ttl > 0 else None
                
            except Exception as e:
                logger.error(f"Error getting TTL for key '{key}' from Redis: {e}")
                return None
        
        # Get from in-memory cache
        if key in self.in_memory_ttl:
            remaining = (self.in_memory_ttl[key] - datetime.now()).total_seconds()
            return int(remaining) if remaining > 0 else None
        
        return None


# Create a singleton instance
cache_service = CacheService()
