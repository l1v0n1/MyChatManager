from typing import Callable, Awaitable, Any, List, Union, Dict, Optional
import functools
from loguru import logger
from aiogram import types
from aiogram.dispatcher.flags import get_flag

from app.config.settings import settings


def admin_required(func: Callable) -> Callable:
    """Decorator to check if user is an admin"""
    @functools.wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        # Get user data from context (middleware adds this)
        user_data = kwargs.get('user', {})
        is_admin = user_data.get('is_admin', False)
        
        # Check if user is in the admin IDs list from settings
        admin_ids = settings.ADMIN_IDS
        user_id = message.from_user.id if message.from_user else None
        
        if is_admin or (user_id and user_id in admin_ids):
            return await func(message, *args, **kwargs)
        else:
            # Not an admin, inform the user
            await message.reply("❌ This command is only available to administrators.")
            return None
    
    # Mark handler with flag
    wrapper.flags = getattr(func, 'flags', {})
    wrapper.flags['admin_required'] = True
    
    return wrapper


def moderator_required(func: Callable) -> Callable:
    """Decorator to check if user is a moderator"""
    @functools.wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        # Get user data from context (middleware adds this)
        user_data = kwargs.get('user', {})
        is_moderator = user_data.get('is_moderator', False)
        
        # Also count admins from settings as moderators
        admin_ids = settings.ADMIN_IDS
        user_id = message.from_user.id if message.from_user else None
        
        if is_moderator or (user_id and user_id in admin_ids):
            return await func(message, *args, **kwargs)
        else:
            # For group chats, also check if the user is a Telegram admin
            chat_member_info = kwargs.get('chat_member', {})
            is_chat_admin = chat_member_info.get('is_admin', False)
            
            if is_chat_admin:
                return await func(message, *args, **kwargs)
            
            # Not a moderator, inform the user
            await message.reply("❌ This command is only available to moderators and administrators.")
            return None
    
    # Mark handler with flag
    wrapper.flags = getattr(func, 'flags', {})
    wrapper.flags['moderator_required'] = True
    
    return wrapper


def rate_limit(limit: int) -> Callable:
    """Decorator to limit request rate
    
    Args:
        limit: Maximum number of requests allowed per minute
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            # The actual rate limiting is handled by RateLimitMiddleware
            return await func(message, *args, **kwargs)
        
        # Mark handler with flag for middleware to use
        wrapper.flags = getattr(func, 'flags', {})
        wrapper.flags['rate_limit'] = limit
        
        return wrapper
    
    return decorator


def log_command(func: Callable) -> Callable:
    """Decorator to log command usage"""
    @functools.wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        # Log command
        user_id = message.from_user.id if message.from_user else "Unknown"
        chat_id = message.chat.id if message.chat else "Unknown"
        chat_type = message.chat.type if message.chat else "Unknown"
        command = message.text.split()[0] if message.text else "Unknown"
        
        logger.info(f"Command {command} used by user {user_id} in chat {chat_id} ({chat_type})")
        
        # Call original function
        return await func(message, *args, **kwargs)
    
    return wrapper


def chat_type(*allowed_types: str) -> Callable:
    """Decorator to restrict commands to specific chat types
    
    Args:
        *allowed_types: Chat types where the command is allowed
            (e.g. "private", "group", "supergroup")
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            if not message.chat or message.chat.type not in allowed_types:
                # Wrong chat type
                chat_type_str = message.chat.type if message.chat else "Unknown"
                
                # Inform user
                allowed_types_str = ", ".join(allowed_types)
                await message.reply(
                    f"❌ This command can only be used in {allowed_types_str} chats.\n"
                    f"Current chat type: {chat_type_str}"
                )
                return None
            
            # Correct chat type, proceed
            return await func(message, *args, **kwargs)
        
        # Mark handler with flag
        wrapper.flags = getattr(func, 'flags', {})
        wrapper.flags['allowed_chat_types'] = allowed_types
        
        return wrapper
    
    return decorator
