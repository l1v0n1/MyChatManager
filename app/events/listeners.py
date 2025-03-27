import asyncio
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, Any

from app.events.event_manager import event_listener, Event
from app.models.user import User, UserRole
from app.models.chat import Chat, ChatMember, ChatMemberStatus


@event_listener("user:join")
async def on_user_join(event: Event) -> None:
    """Handle user join event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    
    logger.info(f"User {user_id} joined chat {chat_id}")
    
    # Here we would update user status in the database
    # and send welcome message if configured


@event_listener("user:leave")
async def on_user_leave(event: Event) -> None:
    """Handle user leave event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    
    logger.info(f"User {user_id} left chat {chat_id}")
    
    # Here we would update user status in the database


@event_listener("message:new")
async def on_new_message(event: Event) -> None:
    """Handle new message event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    message_id = data.get("message_id")
    message_text = data.get("text", "")
    
    logger.debug(f"New message {message_id} in chat {chat_id} from user {user_id}")
    
    # Here we would check for spam, flood, etc.


@event_listener("message:deleted")
async def on_message_deleted(event: Event) -> None:
    """Handle message deleted event"""
    data = event.data
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    
    logger.debug(f"Message {message_id} deleted in chat {chat_id}")


@event_listener("user:warned")
async def on_user_warned(event: Event) -> None:
    """Handle user warned event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    reason = data.get("reason", "Not specified")
    warning_count = data.get("warning_count", 1)
    
    logger.info(f"User {user_id} warned in chat {chat_id} for '{reason}'. Count: {warning_count}")
    
    # Check if user has reached warning threshold
    # If so, trigger ban event


@event_listener("user:banned")
async def on_user_banned(event: Event) -> None:
    """Handle user banned event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    reason = data.get("reason", "Not specified")
    duration = data.get("duration")  # in seconds, None for permanent
    
    if duration:
        ban_until = datetime.now() + timedelta(seconds=duration)
        logger.info(f"User {user_id} banned in chat {chat_id} until {ban_until} for '{reason}'")
    else:
        logger.info(f"User {user_id} permanently banned in chat {chat_id} for '{reason}'")


@event_listener("chat:settings_updated")
async def on_chat_settings_updated(event: Event) -> None:
    """Handle chat settings updated event"""
    data = event.data
    chat_id = data.get("chat_id")
    settings = data.get("settings", {})
    
    logger.info(f"Chat {chat_id} settings updated: {settings}")


@event_listener("spam:detected")
async def on_spam_detected(event: Event) -> None:
    """Handle spam detection event"""
    data = event.data
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")
    message_id = data.get("message_id")
    spam_type = data.get("spam_type", "unknown")
    
    logger.warning(f"Spam detected in chat {chat_id} from user {user_id}, type: {spam_type}")
    
    # Here we would handle auto-deletion of spam and warning/banning user
