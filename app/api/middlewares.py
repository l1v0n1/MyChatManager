from typing import Dict, Any, Callable, Awaitable, Union, Optional
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from loguru import logger
import time
from datetime import datetime

from app.services.user_service import user_service
from app.services.moderation_service import moderation_service
from app.events.event_manager import event_manager
from app.models.user import User, UserRole


class UserUpdateMiddleware(BaseMiddleware):
    """Middleware to update user information on each message"""
    
    async def on_pre_process_message(self, message: types.Message, data: Dict[str, Any]) -> None:
        """Update user info before processing message"""
        if not message.from_user:
            return
        
        # Update or create user in database
        user = await user_service.create_or_update_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code
        )
        
        # Store user in data for handlers
        data['user'] = user
        
        # Check if user is banned
        if user.is_banned:
            # Possibly delete message or take other actions
            logger.warning(f"Banned user {user.id} ({user.username}) attempted to send a message")
            raise CancelHandler()


class ModerationMiddleware(BaseMiddleware):
    """Middleware for spam and flood prevention"""
    
    async def on_pre_process_message(self, message: types.Message, data: Dict[str, Any]) -> None:
        """Check message for spam and flood before processing"""
        # Skip commands
        if message.is_command():
            return
        
        # Skip service messages
        if not message.text and not message.caption:
            return
        
        # Get message text (either text or caption)
        message_text = message.text or message.caption or ""
        
        # Check message
        moderation_result = await moderation_service.check_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            message_text=message_text,
            message_id=message.message_id
        )
        
        # Store moderation result in data
        data['moderation_result'] = moderation_result
        
        # Handle spam/flood if detected
        if moderation_result['should_delete']:
            try:
                # Delete message
                await message.delete()
                
                # Log the action
                logger.warning(
                    f"Deleted message from {message.from_user.id} in chat {message.chat.id}: "
                    f"{moderation_result['reason']}"
                )
                
                # Warn user if needed
                if moderation_result['should_warn']:
                    user = data.get('user')
                    if user:
                        # Warn the user
                        warning_result = await user_service.warn_user(
                            user_id=user.id,
                            chat_id=message.chat.id,
                            reason=moderation_result['reason']
                        )
                        
                        # If user was banned due to warnings, no need to send warning message
                        if not warning_result.get('banned', False):
                            # Send warning message to user
                            await message.answer(
                                f"⚠️ @{message.from_user.username or message.from_user.full_name}, "
                                f"your message was removed: {moderation_result['reason']}\n"
                                f"Warning: {warning_result.get('warnings', 1)}/{warning_result.get('max_warnings', 3)}"
                            )
            
            except Exception as e:
                logger.error(f"Error handling moderation action: {e}")
            
            # Cancel further processing
            raise CancelHandler()


class MetricsMiddleware(BaseMiddleware):
    """Middleware for collecting metrics"""
    
    def __init__(self):
        super().__init__()
        self.start_times: Dict[int, float] = {}
    
    async def on_pre_process_message(self, message: types.Message, data: Dict[str, Any]) -> None:
        """Start timing message processing"""
        self.start_times[message.message_id] = time.time()
    
    async def on_post_process_message(self, message: types.Message, data: Dict[str, Any], result: Any) -> None:
        """Record processing time and other metrics"""
        start_time = self.start_times.pop(message.message_id, None)
        if start_time:
            processing_time = time.time() - start_time
            
            # Log metric
            logger.debug(f"Message processing time: {processing_time:.4f}s | ID: {message.message_id}")
            
            # Here you would collect the metric for monitoring systems like Prometheus
            # metrics.message_processing_time.observe(processing_time)


class I18nMiddleware(BaseMiddleware):
    """Middleware for internationalization"""
    
    def __init__(self, i18n):
        super().__init__()
        self.i18n = i18n
    
    async def on_pre_process_message(self, message: types.Message, data: Dict[str, Any]) -> None:
        """Set user's language for localization"""
        user = data.get('user')
        if user and user.language_code:
            self.i18n.current_locale = user.language_code
