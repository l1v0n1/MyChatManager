from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.markdown import hbold, hcode, hitalic, hlink, hstrikethrough, hunderline
from loguru import logger
from typing import Dict, List, Any, Optional, Union
import asyncio
import time
from datetime import datetime, timedelta

from app.services.user_service import user_service
from app.services.moderation_service import moderation_service
from app.events.event_manager import event_manager
from app.models.user import User, UserRole
from app.models.chat import Chat, ChatMember, ChatMemberStatus
from app.utils.decorators import admin_required, moderator_required, rate_limit, log_command, chat_type


# State machine for user input
class ModeratorActions(StatesGroup):
    waiting_for_ban_reason = State()
    waiting_for_warning_reason = State()
    waiting_for_kick_reason = State()
    waiting_for_mute_time = State()
    waiting_for_mute_reason = State()


# Command handlers
@log_command
async def cmd_start(message: types.Message):
    """Handle /start command"""
    await message.reply(
        f"👋 Welcome to the Chat Manager Bot!\n\n"
        f"I can help you manage your groups with advanced moderation tools.\n"
        f"Use /help to see available commands."
    )


@log_command
async def cmd_help(message: types.Message):
    """Handle /help command"""
    # Get user from context data (added by middleware)
    user_data = message.bot.get('user', {})
    user_role = user_data.get('role', UserRole.MEMBER)
    
    # Basic commands for all users
    help_text = (
        f"📚 {hbold('Available Commands')}\n\n"
        f"General commands:\n"
        f"• /start - Start the bot\n"
        f"• /help - Show this help message\n"
        f"• /rules - Show chat rules\n"
        f"• /report - Report a message (reply to it)\n"
    )
    
    # Commands for moderators and admins
    if user_role in [UserRole.MODERATOR, UserRole.ADMIN]:
        help_text += (
            f"\n{hbold('Moderator Commands')}:\n"
            f"• /warn - Warn a user (reply to their message)\n"
            f"• /mute - Temporarily mute a user\n"
            f"• /unmute - Unmute a user\n"
            f"• /kick - Remove user from chat\n"
        )
    
    # Commands for admins only
    if user_role == UserRole.ADMIN:
        help_text += (
            f"\n{hbold('Admin Commands')}:\n"
            f"• /ban - Ban a user permanently\n"
            f"• /unban - Remove a ban\n"
            f"• /promote - Promote user to moderator\n"
            f"• /demote - Demote moderator to regular user\n"
            f"• /settings - Configure chat settings\n"
        )
    
    await message.reply(help_text, parse_mode=types.ParseMode.HTML)


@log_command
@chat_type("group", "supergroup")
async def cmd_rules(message: types.Message):
    """Handle /rules command"""
    # In a real implementation, this would fetch rules from the database
    # Here we'll use placeholder text
    rules_text = (
        f"📜 {hbold('Chat Rules')}\n\n"
        f"1. Be respectful to all members\n"
        f"2. No spam or flooding\n" 
        f"3. No offensive content\n"
        f"4. No advertising without permission\n"
        f"5. Keep discussions on-topic\n\n"
        f"Violating these rules may result in warnings or bans."
    )
    
    await message.reply(rules_text, parse_mode=types.ParseMode.HTML)


@log_command
@chat_type("group", "supergroup")
@rate_limit(3)
async def cmd_report(message: types.Message):
    """Handle /report command"""
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to the message you want to report.")
        return
    
    reported_user = message.reply_to_message.from_user
    reporter = message.from_user
    
    # Log the report
    logger.info(
        f"Message reported in chat {message.chat.id}: "
        f"Message ID {message.reply_to_message.message_id} "
        f"from user {reported_user.id} by user {reporter.id}"
    )
    
    # Notify admins about the report (in a real implementation, this would DM admins)
    await message.reply(
        f"✅ Report received. A moderator will review it shortly.\n"
        f"Reported message from {reported_user.full_name} has been flagged for review."
    )
    
    # Publish report event
    await event_manager.publish("message:reported", {
        "chat_id": message.chat.id,
        "message_id": message.reply_to_message.message_id,
        "reported_user_id": reported_user.id,
        "reported_by_id": reporter.id,
        "timestamp": datetime.now().isoformat()
    })


@log_command
@chat_type("group", "supergroup")
@moderator_required
async def cmd_warn(message: types.Message, state: FSMContext):
    """Handle /warn command"""
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to a message from the user you want to warn.")
        return
    
    target_user = message.reply_to_message.from_user
    
    # Store target user info in state
    await state.update_data(target_user_id=target_user.id, target_message_id=message.reply_to_message.message_id)
    
    # Ask for reason
    await message.reply(f"Please provide a reason for warning {target_user.full_name}:")
    
    # Set state to waiting for reason
    await ModeratorActions.waiting_for_warning_reason.set()


@log_command
@chat_type("group", "supergroup")
@moderator_required
async def process_warning_reason(message: types.Message, state: FSMContext):
    """Process warning reason"""
    # Get data from state
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    target_message_id = data.get('target_message_id')
    reason = message.text
    
    # Reset state
    await state.finish()
    
    if not target_user_id:
        await message.reply("⚠️ Error: Could not find target user information.")
        return
    
    # Get users from database
    target_user = await user_service.get_user_by_telegram_id(target_user_id)
    if not target_user:
        await message.reply("⚠️ Error: Target user not found in database.")
        return
    
    # Warn user
    warning_result = await user_service.warn_user(
        user_id=target_user.id,
        chat_id=message.chat.id,
        reason=reason
    )
    
    if warning_result.get('success', False):
        if warning_result.get('banned', False):
            await message.reply(
                f"⚠️ User {target_user.full_name} has been warned and banned for: {reason}\n"
                f"This was their {warning_result.get('warnings')}th warning, exceeding the limit."
            )
        else:
            await message.reply(
                f"⚠️ User {target_user.full_name} has been warned for: {reason}\n"
                f"Warning count: {warning_result.get('warnings')}/{warning_result.get('max_warnings', 3)}"
            )
    else:
        await message.reply(f"❌ Failed to warn user: {warning_result.get('message', 'Unknown error')}")


@log_command
@chat_type("group", "supergroup")
@moderator_required
async def cmd_mute(message: types.Message, state: FSMContext):
    """Handle /mute command"""
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to a message from the user you want to mute.")
        return
    
    target_user = message.reply_to_message.from_user
    
    # Store target user info in state
    await state.update_data(target_user_id=target_user.id)
    
    # Ask for mute duration
    await message.reply(
        f"How long do you want to mute {target_user.full_name}?\n"
        f"Examples: 1h, 30m, 1d, 10m30s"
    )
    
    # Set state to waiting for mute time
    await ModeratorActions.waiting_for_mute_time.set()


@log_command
async def process_mute_time(message: types.Message, state: FSMContext):
    """Process mute time"""
    # Parse duration from text
    time_text = message.text.lower().strip()
    seconds = 0
    
    try:
        # Simple duration parser
        if 'd' in time_text:
            days_str = time_text.split('d')[0].strip()
            if days_str:
                seconds += int(days_str) * 86400
            time_text = time_text.split('d')[1]
        
        if 'h' in time_text:
            hours_str = time_text.split('h')[0].strip()
            if hours_str:
                seconds += int(hours_str) * 3600
            time_text = time_text.split('h')[1]
        
        if 'm' in time_text:
            minutes_str = time_text.split('m')[0].strip()
            if minutes_str:
                seconds += int(minutes_str) * 60
            time_text = time_text.split('m')[1]
        
        if 's' in time_text:
            seconds_str = time_text.split('s')[0].strip()
            if seconds_str:
                seconds += int(seconds_str)
        
        # If no unit specified, assume minutes
        if time_text.isdigit():
            seconds = int(time_text) * 60
    
    except ValueError:
        await message.reply("⚠️ Invalid time format. Please use format like: 1h, 30m, 1d, etc.")
        await state.finish()
        return
    
    if seconds < 30:
        await message.reply("⚠️ Minimum mute duration is 30 seconds.")
        await state.finish()
        return
    
    if seconds > 86400 * 30:  # 30 days
        await message.reply("⚠️ Maximum mute duration is 30 days.")
        await state.finish()
        return
    
    # Update state with mute duration
    await state.update_data(mute_duration=seconds)
    
    # Get data from state
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    
    # Format duration for display
    duration_str = format_duration(seconds)
    
    # Ask for reason
    await message.reply(f"Please provide a reason for muting the user for {duration_str}:")
    
    # Set state to waiting for reason
    await ModeratorActions.waiting_for_mute_reason.set()


@log_command
async def process_mute_reason(message: types.Message, state: FSMContext):
    """Process mute reason and apply mute"""
    # Get data from state
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    mute_duration = data.get('mute_duration', 300)  # Default 5 minutes
    reason = message.text
    
    # Reset state
    await state.finish()
    
    if not target_user_id:
        await message.reply("⚠️ Error: Could not find target user information.")
        return
    
    # Format duration for display
    duration_str = format_duration(mute_duration)
    
    # In a real implementation, this would mute the user in Telegram using restrict_chat_member
    # and update the database with mute information
    
    try:
        # Restrict user's permissions
        await message.chat.restrict(
            user_id=target_user_id,
            permissions=types.ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            ),
            until_date=datetime.now() + timedelta(seconds=mute_duration)
        )
        
        # Publish mute event
        await event_manager.publish("user:muted", {
            "chat_id": message.chat.id,
            "user_id": target_user_id,
            "duration": mute_duration,
            "reason": reason,
            "muted_by": message.from_user.id,
            "until": (datetime.now() + timedelta(seconds=mute_duration)).isoformat()
        })
        
        # Send confirmation
        await message.reply(
            f"🔇 User has been muted for {duration_str} for: {reason}\n"
            f"They will be automatically unmuted after this period."
        )
        
    except Exception as e:
        logger.error(f"Failed to mute user: {e}")
        await message.reply(f"❌ Failed to mute user: {str(e)}")


@log_command
@chat_type("group", "supergroup")
@moderator_required
async def cmd_unmute(message: types.Message):
    """Handle /unmute command"""
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to a message from the user you want to unmute.")
        return
    
    target_user = message.reply_to_message.from_user
    
    try:
        # Restore user's permissions
        await message.chat.restrict(
            user_id=target_user.id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        
        # Publish unmute event
        await event_manager.publish("user:unmuted", {
            "chat_id": message.chat.id,
            "user_id": target_user.id,
            "unmuted_by": message.from_user.id
        })
        
        await message.reply(f"🔊 User {target_user.full_name} has been unmuted.")
        
    except Exception as e:
        logger.error(f"Failed to unmute user: {e}")
        await message.reply(f"❌ Failed to unmute user: {str(e)}")


@log_command
@chat_type("group", "supergroup")
@admin_required
async def cmd_ban(message: types.Message, state: FSMContext):
    """Handle /ban command"""
    # Check if message is a reply
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to a message from the user you want to ban.")
        return
    
    target_user = message.reply_to_message.from_user
    
    # Store target user info in state
    await state.update_data(target_user_id=target_user.id)
    
    # Ask for reason
    await message.reply(f"Please provide a reason for banning {target_user.full_name}:")
    
    # Set state to waiting for reason
    await ModeratorActions.waiting_for_ban_reason.set()


@log_command
async def process_ban_reason(message: types.Message, state: FSMContext):
    """Process ban reason and apply ban"""
    # Get data from state
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    reason = message.text
    
    # Reset state
    await state.finish()
    
    if not target_user_id:
        await message.reply("⚠️ Error: Could not find target user information.")
        return
    
    try:
        # Ban user from chat
        await message.chat.kick(user_id=target_user_id)
        
        # Get user from database
        target_user = await user_service.get_user_by_telegram_id(target_user_id)
        if target_user:
            # Ban in database
            ban_result = await user_service.ban_user(
                user_id=target_user.id,
                chat_id=message.chat.id,
                reason=reason
            )
            
            if ban_result:
                await message.reply(f"🚫 User has been banned from this chat for: {reason}")
            else:
                await message.reply("❌ Failed to update ban status in database.")
        else:
            await message.reply("⚠️ User was banned, but they were not found in the database.")
        
    except Exception as e:
        logger.error(f"Failed to ban user: {e}")
        await message.reply(f"❌ Failed to ban user: {str(e)}")


# Register all handlers
def register_handlers(dp: Dispatcher):
    """Register all message handlers"""
    # Basic commands
    dp.register_message_handler(cmd_start, commands=["start"])
    dp.register_message_handler(cmd_help, commands=["help"])
    dp.register_message_handler(cmd_rules, commands=["rules"])
    dp.register_message_handler(cmd_report, commands=["report"])
    
    # Moderation commands
    dp.register_message_handler(cmd_warn, commands=["warn"])
    dp.register_message_handler(cmd_mute, commands=["mute"])
    dp.register_message_handler(cmd_unmute, commands=["unmute"])
    dp.register_message_handler(cmd_ban, commands=["ban"])
    
    # State handlers
    dp.register_message_handler(process_warning_reason, state=ModeratorActions.waiting_for_warning_reason)
    dp.register_message_handler(process_mute_time, state=ModeratorActions.waiting_for_mute_time)
    dp.register_message_handler(process_mute_reason, state=ModeratorActions.waiting_for_mute_reason)
    dp.register_message_handler(process_ban_reason, state=ModeratorActions.waiting_for_ban_reason)


# Helper function to format duration
def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string"""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes == 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if hours == 0:
            return f"{days} day{'s' if days != 1 else ''}"
        return f"{days} day{'s' if days != 1 else ''} and {hours} hour{'s' if hours != 1 else ''}"
