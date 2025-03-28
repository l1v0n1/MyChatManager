from typing import Dict, Any, Optional, Tuple
from loguru import logger
from datetime import datetime
import time
import asyncio
import math

from app.services.cache_service import cache_service


class RateLimitService:
    """Service for rate limiting requests"""
    
    async def check_rate_limit(self, key: str, limit: int, period: int) -> bool:
        """
        Check if a request exceeds the rate limit
        
        Args:
            key: Unique identifier for this rate limit (usually contains user ID and action)
            limit: Maximum number of requests allowed in the period
            period: Time period in seconds
            
        Returns:
            bool: True if rate limit is exceeded, False otherwise
        """
        # Get current timestamp
        now = time.time()
        
        # Get the current count and window start time from cache
        cache_key = f"ratelimit:{key}"
        rate_data = await cache_service.get(cache_key)
        
        if rate_data is None:
            # First request in this window
            rate_data = {
                "count": 1,
                "window_start": now,
                "last_request": now
            }
            
            # Store in cache
            await cache_service.set(
                key=cache_key,
                value=rate_data,
                ttl=period
            )
            
            # Not limited
            return False
        
        # Check if we're in a new window
        window_elapsed = now - rate_data["window_start"]
        if window_elapsed > period:
            # Start a new window
            rate_data = {
                "count": 1,
                "window_start": now,
                "last_request": now
            }
            
            # Store in cache
            await cache_service.set(
                key=cache_key,
                value=rate_data,
                ttl=period
            )
            
            # Not limited
            return False
        
        # We're in the same window, increment the counter
        rate_data["count"] += 1
        rate_data["last_request"] = now
        
        # Store updated data
        await cache_service.set(
            key=cache_key,
            value=rate_data,
            ttl=period
        )
        
        # Check if we've exceeded the limit
        return rate_data["count"] > limit
    
    async def get_cooldown(self, key: str) -> int:
        """
        Get the remaining cooldown time in seconds
        
        Args:
            key: The rate limit key
            
        Returns:
            int: Seconds remaining in the cooldown period, or 0 if no cooldown
        """
        # Get rate limit data from cache
        cache_key = f"ratelimit:{key}"
        rate_data = await cache_service.get(cache_key)
        
        if not rate_data:
            return 0
        
        # Calculate cooldown based on the window start time and period
        now = time.time()
        window_start = rate_data.get("window_start", now)
        period = await cache_service.get_ttl(cache_key)
        
        # Calculate time remaining in the window
        elapsed = now - window_start
        remaining = max(0, math.ceil(period - elapsed))
        
        return remaining
    
    async def reset_rate_limit(self, key: str) -> bool:
        """
        Reset a rate limit counter
        
        Args:
            key: The rate limit key to reset
            
        Returns:
            bool: True if successfully reset, False otherwise
        """
        cache_key = f"ratelimit:{key}"
        return await cache_service.delete(cache_key)


# Create a singleton instance
rate_limit_service = RateLimitService() 