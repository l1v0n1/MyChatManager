import re
from typing import Dict, List, Optional, Tuple, Set, Any
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import time
from dataclasses import dataclass, field

from app.events.event_manager import event_manager
from app.services.cache_service import cache_service
from app.models.chat import Chat
from app.config.settings import settings


@dataclass
class UserMessageStats:
    """User message statistics for flood detection"""
    messages: List[float] = field(default_factory=list)
    last_message_time: Optional[float] = None
    warning_count: int = 0
    

class ModerationService:
    """Service for chat moderation, spam detection, and anti-flood"""
    
    def __init__(self):
        """Initialize the moderation service"""
        # Regular expressions for basic spam detection
        self.url_pattern = re.compile(r'https?://\S+|www\.\S+')
        self.spam_patterns = [
            # Common spam patterns
            re.compile(r'buy.{1,20}followers', re.IGNORECASE),
            re.compile(r'make money online', re.IGNORECASE),
            re.compile(r'earn \$\d+ per day', re.IGNORECASE),
            re.compile(r'join my channel', re.IGNORECASE),
            re.compile(r'click here', re.IGNORECASE),
            # Add more patterns as needed
        ]
        
        # Flood prevention
        self.user_message_stats: Dict[Tuple[int, int], UserMessageStats] = {}  # (chat_id, user_id) -> stats
        self.flood_expiry_time = 60  # seconds to keep message history
    
    async def check_message(self, chat_id: int, user_id: int, message_text: str, message_id: int) -> Dict[str, Any]:
        """
        Check message for spam and flood.
        Returns a dict with the results of the check.
        """
        result = {
            "is_spam": False,
            "spam_type": None,
            "is_flood": False,
            "should_delete": False,
            "should_warn": False,
            "reason": None
        }
        
        # Get chat settings from cache or DB
        chat_settings = await self._get_chat_settings(chat_id)
        
        # Skip checks if moderation is disabled for this chat
        if not chat_settings.get('anti_spam_enabled', True) and not chat_settings.get('anti_flood_enabled', True):
            return result
        
        # Check for spam if enabled
        if chat_settings.get('anti_spam_enabled', True):
            spam_check = await self._check_spam(message_text)
            if spam_check['is_spam']:
                result.update(spam_check)
                result['should_delete'] = True
                result['should_warn'] = True
                
                # Publish spam detection event
                await event_manager.publish("spam:detected", {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "message_id": message_id,
                    "spam_type": spam_check['spam_type'],
                    "timestamp": datetime.now().isoformat()
                })
                
                return result
        
        # Check for flood if enabled
        if chat_settings.get('anti_flood_enabled', True):
            flood_threshold = chat_settings.get('flood_threshold', 5)  # Default: 5 messages per second
            flood_check = await self._check_flood(chat_id, user_id, flood_threshold)
            if flood_check['is_flood']:
                result.update(flood_check)
                result['should_delete'] = True
                result['should_warn'] = flood_check['warning_count'] % 3 == 0  # Warn every 3 flood messages
                
                # Publish flood detection event
                await event_manager.publish("flood:detected", {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "message_id": message_id,
                    "messages_per_second": flood_check.get('messages_per_second', 0),
                    "warning_count": flood_check.get('warning_count', 0),
                    "timestamp": datetime.now().isoformat()
                })
                
                return result
        
        return result
    
    async def _check_spam(self, message_text: str) -> Dict[str, Any]:
        """Check if a message contains spam"""
        result = {
            "is_spam": False,
            "spam_type": None,
            "reason": None
        }
        
        # Check against spam patterns
        for pattern in self.spam_patterns:
            if pattern.search(message_text):
                result['is_spam'] = True
                result['spam_type'] = 'pattern'
                result['reason'] = f"Matched spam pattern: {pattern.pattern}"
                return result
        
        # Check for excessive URLs
        urls = self.url_pattern.findall(message_text)
        if len(urls) > 3:  # More than 3 URLs is suspicious
            result['is_spam'] = True
            result['spam_type'] = 'excessive_urls'
            result['reason'] = f"Excessive URLs: {len(urls)}"
            return result
        
        # Check for caps
        if len(message_text) > 15:  # Only check longer messages
            caps_ratio = sum(1 for c in message_text if c.isupper()) / len(message_text)
            if caps_ratio > 0.7:  # 70% or more uppercase
                result['is_spam'] = True
                result['spam_type'] = 'excessive_caps'
                result['reason'] = f"Excessive uppercase ({int(caps_ratio * 100)}%)"
                return result
        
        return result
    
    async def _check_flood(self, chat_id: int, user_id: int, threshold: int = 5) -> Dict[str, Any]:
        """Check if a user is flooding the chat"""
        result = {
            "is_flood": False,
            "reason": None,
            "messages_per_second": 0,
            "warning_count": 0
        }
        
        key = (chat_id, user_id)
        current_time = time.time()
        
        # Initialize user stats if not exists
        if key not in self.user_message_stats:
            self.user_message_stats[key] = UserMessageStats()
        
        user_stats = self.user_message_stats[key]
        user_stats.last_message_time = current_time
        user_stats.messages.append(current_time)
        
        # Clean old messages (older than flood_expiry_time)
        user_stats.messages = [
            t for t in user_stats.messages 
            if current_time - t < self.flood_expiry_time
        ]
        
        # Calculate messages per second in last 3 seconds
        recent_messages = [
            t for t in user_stats.messages 
            if current_time - t <= 3
        ]
        if len(recent_messages) >= threshold:
            seconds = max(1, current_time - min(recent_messages))
            msgs_per_second = len(recent_messages) / seconds
            
            if msgs_per_second >= threshold:
                user_stats.warning_count += 1
                result['is_flood'] = True
                result['messages_per_second'] = msgs_per_second
                result['reason'] = f"Sending too many messages ({msgs_per_second:.1f}/second)"
                result['warning_count'] = user_stats.warning_count
        
        return result
    
    async def _get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        """Get chat moderation settings from cache or database"""
        # Try to get from cache first
        cache_key = f"chat:settings:{chat_id}"
        settings = await cache_service.get_json(cache_key)
        
        if settings:
            return settings
        
        # If not in cache, query database
        # In a real implementation, this would query the database
        # For now, return default settings
        default_settings = {
            "anti_spam_enabled": True,
            "anti_flood_enabled": True,
            "flood_threshold": 5,
            "max_warnings": 3,
            "auto_delete_service_messages": True,
            "auto_delete_join_messages": True
        }
        
        # Cache the settings
        await cache_service.set_json(cache_key, default_settings)
        
        return default_settings
    
    async def clean_expired_stats(self) -> None:
        """Clean expired user message stats (periodic task)"""
        current_time = time.time()
        
        # Find keys to remove
        to_remove = []
        for key, stats in self.user_message_stats.items():
            if stats.last_message_time and current_time - stats.last_message_time > self.flood_expiry_time:
                to_remove.append(key)
        
        # Remove expired stats
        for key in to_remove:
            del self.user_message_stats[key]
        
        if to_remove:
            logger.debug(f"Cleaned {len(to_remove)} expired user message stats")


# Create singleton instance
moderation_service = ModerationService()
