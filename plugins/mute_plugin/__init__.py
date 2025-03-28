"""
Mute Plugin for MyChatManager
Adds enhanced muting functionality with scheduled unmute and reasons tracking
"""
from typing import Dict, Callable, Any, List
from datetime import datetime, timedelta
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
import re

from app.plugins.plugin_manager import PluginBase, PluginMetadata
from app.services.user_service import user_service
from app.models.user import User, UserRole
from app.utils.decorators import moderator_required, log_command, chat_type


class MuteStates(StatesGroup):
    """States for mute command flow"""
    waiting_for_duration = State()
    waiting_for_reason = State()


class MutePlugin(PluginBase):
    """Plugin for enhanced mute functionality"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="mute_plugin",
        version="1.0.0",
        description="Enhanced mute commands with scheduled unmute and reasons tracking",
        author="MyChatManager Team",
        requires=[],
        conflicts=[]
    )
    
    def __init__(self, manager):
        """Initialize the plugin"""
        super().__init__(manager)
        self.router = Router(name="mute_plugin")
        self.active_mutes = {}  # user_id -> unmute_time
        self.mute_tasks = {}    # user_id -> asyncio task
        
        # Register handlers
        self.router.message(Command("tempmute"))(self.cmd_tempmute)
        self.router.message(MuteStates.waiting_for_duration)(self.process_mute_duration)
        self.router.message(MuteStates.waiting_for_reason)(self.process_mute_reason)
        self.router.callback_query(F.data.startswith("mute_"))(self.mute_callback_handler)
    
    async def activate(self) -> bool:
        """Activate the plugin"""
        logger.info(f"Activating {self.metadata.name} plugin...")
        return await super().activate()
    
    async def deactivate(self) -> bool:
        """Deactivate the plugin"""
        # Cancel all mute tasks
        for task in self.mute_tasks.values():
            if not task.done():
                task.cancel()
        
        return await super().deactivate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {
            "tempmute": self.cmd_tempmute
        }
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_tempmute(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /tempmute command with preset durations"""
        # Check if message is a reply
        if not message.reply_to_message:
            await message.reply("⚠️ Please reply to a message from the user you want to mute.")
            return
        
        target_user = message.reply_to_message.from_user
        
        # Store target user info in state
        await state.update_data(target_user_id=target_user.id)
        
        # Create keyboard with preset durations
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="5 minutes", callback_data=f"mute_300_{target_user.id}"),
                InlineKeyboardButton(text="15 minutes", callback_data=f"mute_900_{target_user.id}"),
                InlineKeyboardButton(text="30 minutes", callback_data=f"mute_1800_{target_user.id}")
            ],
            [
                InlineKeyboardButton(text="1 hour", callback_data=f"mute_3600_{target_user.id}"),
                InlineKeyboardButton(text="3 hours", callback_data=f"mute_10800_{target_user.id}"),
                InlineKeyboardButton(text="12 hours", callback_data=f"mute_43200_{target_user.id}")
            ],
            [
                InlineKeyboardButton(text="1 day", callback_data=f"mute_86400_{target_user.id}"),
                InlineKeyboardButton(text="1 week", callback_data=f"mute_604800_{target_user.id}"),
                InlineKeyboardButton(text="Custom", callback_data=f"mute_custom_{target_user.id}")
            ]
        ])
        
        await message.reply(
            f"For how long do you want to mute {target_user.full_name}?\n"
            f"Choose a duration or select 'Custom' to specify:",
            reply_markup=keyboard
        )
    
    async def mute_callback_handler(self, callback: CallbackQuery, state: FSMContext):
        """Handle mute duration selection from inline keyboard"""
        # Parse callback data: mute_duration_userid
        parts = callback.data.split('_')
        if len(parts) != 3:
            await callback.answer("Invalid callback data", show_alert=True)
            return
        
        _, duration_str, target_user_id = parts
        
        await callback.answer()
        
        if duration_str == "custom":
            # Ask for custom duration
            await callback.message.edit_text(
                f"Please specify a custom mute duration.\n"
                f"Examples: 1h, 30m, 1d, 10m30s"
            )
            
            # Store user ID in state
            await state.update_data(target_user_id=int(target_user_id))
            
            # Set state to wait for duration
            await state.set_state(MuteStates.waiting_for_duration)
        else:
            # Preset duration selected
            duration = int(duration_str)
            
            # Store mute info in state
            await state.update_data(
                target_user_id=int(target_user_id),
                mute_duration=duration
            )
            
            # Ask for reason
            duration_str = self.format_duration(duration)
            await callback.message.edit_text(
                f"Please provide a reason for muting the user for {duration_str}:"
            )
            
            # Set state to wait for reason
            await state.set_state(MuteStates.waiting_for_reason)
    
    async def process_mute_duration(self, message: Message, state: FSMContext):
        """Process custom mute duration"""
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
            await state.clear()
            return
        
        if seconds < 30:
            await message.reply("⚠️ Minimum mute duration is 30 seconds.")
            await state.clear()
            return
        
        if seconds > 86400 * 30:  # 30 days
            await message.reply("⚠️ Maximum mute duration is 30 days.")
            await state.clear()
            return
        
        # Update state with mute duration
        await state.update_data(mute_duration=seconds)
        
        # Format duration for display
        duration_str = self.format_duration(seconds)
        
        # Ask for reason
        await message.reply(f"Please provide a reason for muting the user for {duration_str}:")
        
        # Set state to waiting for reason
        await state.set_state(MuteStates.waiting_for_reason)
    
    async def process_mute_reason(self, message: Message, state: FSMContext):
        """Process mute reason and apply mute"""
        # Get data from state
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        mute_duration = data.get('mute_duration', 300)  # Default 5 minutes
        reason = message.text
        
        # Reset state
        await state.clear()
        
        if not target_user_id:
            await message.reply("⚠️ Error: Could not find target user information.")
            return
        
        # Format duration for display
        duration_str = self.format_duration(mute_duration)
        
        try:
            # Restrict user's permissions
            from aiogram.types import ChatPermissions
            
            # Set unmute time
            unmute_time = datetime.now() + timedelta(seconds=mute_duration)
            
            # Mute user
            await message.chat.restrict(
                user_id=target_user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                ),
                until_date=unmute_time
            )
            
            # Save mute info
            self.active_mutes[target_user_id] = unmute_time
            
            # Schedule unmute task (as backup in case Telegram's scheduling fails)
            if target_user_id in self.mute_tasks:
                if not self.mute_tasks[target_user_id].done():
                    self.mute_tasks[target_user_id].cancel()
            
            # Create task for unmuting
            self.mute_tasks[target_user_id] = asyncio.create_task(
                self.schedule_unmute(message.chat.id, target_user_id, mute_duration)
            )
            
            # Log to database
            target_user = await user_service.get_user_by_telegram_id(target_user_id)
            if target_user:
                # In a real implementation, we would log the mute to the database
                logger.info(f"User {target_user_id} muted for {duration_str} by {message.from_user.id}: {reason}")
            
            # Send confirmation
            await message.reply(
                f"🔇 User has been muted for {duration_str} for: {reason}\n"
                f"They will be automatically unmuted at {unmute_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
        except Exception as e:
            logger.error(f"Failed to mute user: {e}")
            await message.reply(f"❌ Failed to mute user: {str(e)}")
    
    async def schedule_unmute(self, chat_id: int, user_id: int, duration: int):
        """Schedule an unmute after the specified duration"""
        try:
            # Wait for the mute duration
            await asyncio.sleep(duration)
            
            # Check if the user is still muted (could have been manually unmuted)
            if user_id in self.active_mutes:
                # Restore user's permissions
                from aiogram.types import ChatPermissions
                
                # Get bot from the plugin manager's context
                # Note: This assumes the bot instance is available 
                from app.api.bot import bot
                
                if bot:
                    try:
                        await bot.restrict_chat_member(
                            chat_id=chat_id,
                            user_id=user_id,
                            permissions=ChatPermissions(
                                can_send_messages=True,
                                can_send_media_messages=True,
                                can_send_other_messages=True,
                                can_add_web_page_previews=True
                            )
                        )
                        logger.info(f"User {user_id} automatically unmuted after duration")
                        
                        # Remove from active mutes
                        del self.active_mutes[user_id]
                        
                    except Exception as e:
                        logger.error(f"Error during scheduled unmute: {e}")
        
        except asyncio.CancelledError:
            # Task was cancelled, cleanup
            logger.debug(f"Unmute task for user {user_id} cancelled")
        except Exception as e:
            logger.error(f"Error in unmute scheduler: {e}")
    
    def format_duration(self, seconds: int) -> str:
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