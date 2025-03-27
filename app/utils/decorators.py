from functools import wraps
import asyncio
from typing import Callable, Dict, Any, Optional, List, Union
import time
from loguru import logger
from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.utils.exceptions import Throttled

from app.models.user import UserRole
from app.services.user_service import user_service


def admin_required(func):
    """Decorator to restrict access to admin users only"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user or user.role != UserRole.ADMIN:
            await message.reply("⚠️ This command is only available to administrators.")
            return
        
        return await func(message, *args, **kwargs)
    
    return wrapper


def moderator_required(func):
    """Decorator to restrict access to moderators and admins"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if not user or (user.role != UserRole.ADMIN and user.role != UserRole.MODERATOR):
            await message.reply("⚠️ This command is only available to moderators and administrators.")
            return
        
        return await func(message, *args, **kwargs)
    
    return wrapper


def rate_limit(limit: int, key=None):
    """
    Decorator for rate limiting.
    :param limit: Maximum number of calls per minute
    :param key: If None, rate limit is per-function, otherwise per provided key
    """
    def decorator(func):
        # Store last call timestamps per key
        setattr(func, '_last_call_times', {})
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_call_times = getattr(func, '_last_call_times')
            
            # Determine the rate limit key
            if len(args) > 0 and isinstance(args[0], types.Message):
                # If first arg is a message, use user ID as key
                rate_key = f"{key or func.__name__}:{args[0].from_user.id}"
            else:
                # Otherwise use function name as key
                rate_key = f"{key or func.__name__}"
            
            current_time = time.time()
            
            # Clean old timestamps (older than 60 seconds)
            for k in list(last_call_times.keys()):
                if current_time - last_call_times[k][-1] > 60:
                    last_call_times.pop(k, None)
            
            # Get call times for this key
            call_times = last_call_times.get(rate_key, [])
            
            # Remove calls older than 60 seconds
            call_times = [t for t in call_times if current_time - t <= 60]
            
            # Check if limit exceeded
            if len(call_times) >= limit:
                if isinstance(args[0], types.Message):
                    await args[0].reply(f"⚠️ Rate limit exceeded. Please wait before using this command again.")
                return
            
            # Add current call time
            call_times.append(current_time)
            last_call_times[rate_key] = call_times
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def log_command(func):
    """Decorator to log command usage"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        logger.info(
            f"Command: {message.get_command()} | "
            f"User: {message.from_user.id} ({message.from_user.username or message.from_user.full_name}) | "
            f"Chat: {message.chat.id} ({message.chat.type})"
        )
        return await func(message, *args, **kwargs)
    
    return wrapper


def chat_type(*chat_types: str):
    """
    Decorator to restrict handlers to specified chat types
    E.g. @chat_type("private") or @chat_type("group", "supergroup")
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            if message.chat.type not in chat_types:
                allowed = ", ".join(chat_types)
                await message.reply(f"⚠️ This command can only be used in {allowed} chats.")
                return
            
            return await func(message, *args, **kwargs)
        
        return wrapper
    
    return decorator
