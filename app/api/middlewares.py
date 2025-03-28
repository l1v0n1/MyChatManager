from typing import Dict, Any, Callable, Awaitable, Union, Optional, cast
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update
from aiogram.dispatcher.flags import get_flag
import time
from datetime import datetime
import asyncio
from loguru import logger

from app.services.user_service import user_service
from app.services.moderation_service import moderation_service
from app.events.event_manager import event_manager
from app.models.user import User, UserRole
from app.services.chat_service import chat_service
from app.services.rate_limit_service import rate_limit_service


class UserUpdateMiddleware(BaseMiddleware):
    """Middleware to update user information on each message"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Update user info before processing message"""
        if isinstance(event, Message) and event.from_user:
            # Update or create user in database
            user = await user_service.create_or_update_user(
                telegram_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                last_name=event.from_user.last_name,
                language_code=event.from_user.language_code
            )
            
            # Store user in data for handlers
            data['user'] = user
            
            # Check if user is banned
            if user.is_banned:
                # Possibly delete message or take other actions
                logger.warning(f"Banned user {user.id} ({user.username}) attempted to send a message")
                return None
        
        # Continue processing
        return await handler(event, data)


class ModerationMiddleware(BaseMiddleware):
    """Middleware for spam and flood prevention"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Check message for spam and flood before processing"""
        if isinstance(event, Message):
            message = event
            
            # Skip commands
            if message.is_command():
                return await handler(message, data)
            
            # Skip service messages
            if not message.text and not message.caption:
                return await handler(message, data)
            
            # Get message text (either text or caption)
            message_text = message.text or message.caption or ""
            
            try:
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
                        
                        # Don't process the message further
                        return None
                        
                    except Exception as e:
                        logger.error(f"Error handling moderation action: {e}")
            except Exception as e:
                logger.error(f"Error in moderation middleware: {e}")
        
        # Continue processing if no issues
        return await handler(event, data)


class MetricsMiddleware(BaseMiddleware):
    """Middleware for collecting metrics"""
    
    def __init__(self):
        self.start_times: Dict[int, float] = {}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Record processing time and other metrics"""
        # Start timing
        start_time = time.time()
        message_id = None
        
        # Only track timing for message events
        if isinstance(event, Message):
            message_id = event.message_id
        
        # Process the event
        result = await handler(event, data)
        
        # Record processing time
        if message_id:
            processing_time = time.time() - start_time
            
            # Log metric
            logger.debug(f"Message processing time: {processing_time:.4f}s | ID: {message_id}")
            
            # Here you would collect the metric for monitoring systems like Prometheus
            # metrics.message_processing_time.observe(processing_time)
        
        return result


class I18nMiddleware(BaseMiddleware):
    """Middleware for internationalization"""
    
    def __init__(self, i18n):
        self.i18n = i18n
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Set user's language for localization"""
        # Set language based on user
        if isinstance(event, Message) and event.from_user:
            user = data.get('user')
            if user and user.language_code:
                self.i18n.current_locale = user.language_code
        
        # Process the event
        return await handler(event, data)


class UserContextMiddleware(BaseMiddleware):
    """Middleware to add user data to message context"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Process update and inject user data into context"""
        # Check if there's a Message object
        if isinstance(event, Message):
            message = event
            user = message.from_user
            
            if user:
                # Get or create user in database
                db_user = await user_service.get_or_create_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name
                )
                
                # Add user to context
                data["user"] = {
                    "id": db_user.id,
                    "telegram_id": db_user.telegram_id,
                    "username": db_user.username,
                    "role": db_user.role,
                    "is_admin": db_user.role == UserRole.ADMIN,
                    "is_moderator": db_user.role in [UserRole.ADMIN, UserRole.MODERATOR]
                }
                
                # For group chats, check if user is admin in Telegram
                if message.chat and message.chat.type in ["group", "supergroup"]:
                    # Get or create chat in database
                    db_chat = await chat_service.get_or_create_chat(
                        telegram_id=message.chat.id,
                        title=message.chat.title,
                        chat_type=message.chat.type
                    )
                    
                    # Add chat to context
                    data["chat"] = {
                        "id": db_chat.id,
                        "telegram_id": db_chat.telegram_id,
                        "title": db_chat.title,
                        "type": db_chat.chat_type
                    }
                    
                    # Check user permissions in chat
                    try:
                        chat_member = await message.chat.get_member(user.id)
                        is_admin = chat_member.status in ["creator", "administrator"]
                        
                        # Add chat member info to context
                        data["chat_member"] = {
                            "status": chat_member.status,
                            "is_admin": is_admin
                        }
                        
                        # Update database with chat member info
                        await chat_service.update_chat_member(
                            chat_id=db_chat.id,
                            user_id=db_user.id,
                            status=chat_member.status
                        )
                    except Exception as e:
                        logger.error(f"Error getting chat member: {e}")
        
        # Continue processing
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Middleware to limit requests based on user ID"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Check rate limits and process update if allowed"""
        # Only rate limit messages with the rate_limit flag
        rate_limit = get_flag(data, "rate_limit")
        
        if rate_limit is None:
            # No rate limit specified, continue as normal
            return await handler(event, data)
        
        # Get user ID for rate limiting
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        
        if not user_id:
            # Can't rate limit without user ID, continue as normal
            return await handler(event, data)
        
        # Check if rate limited
        key = f"rate_limit:{handler.__name__}:{user_id}"
        limit_requests = rate_limit if isinstance(rate_limit, int) else 1
        limit_period = 60  # 1 minute default
        
        # Check if we've hit the rate limit
        is_limited = await rate_limit_service.check_rate_limit(
            key=key,
            limit=limit_requests,
            period=limit_period
        )
        
        if is_limited:
            # User is rate limited
            if isinstance(event, Message):
                # Inform user they're rate limited
                cooldown = await rate_limit_service.get_cooldown(key)
                await event.reply(
                    f"⚠️ Rate limit exceeded. Please wait {cooldown} seconds before trying again."
                )
            
            # Don't process the update
            return None
        
        # Process update
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """Middleware to log all incoming updates for debugging"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Log update and process it"""
        # Log basic info about the update
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else "Unknown"
            chat_id = event.chat.id if event.chat else "Unknown"
            message_text = event.text or event.caption or "[No text]"
            
            if len(message_text) > 100:
                message_text = message_text[:97] + "..."
            
            logger.info(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Message from user {user_id} in chat {chat_id}: {message_text}"
            )
        else:
            # Log other update types
            logger.info(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Received update of type {type(event).__name__}"
            )
        
        # Continue processing
        return await handler(event, data)
