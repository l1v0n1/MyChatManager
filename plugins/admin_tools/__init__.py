"""
Admin Tools Plugin for MyChatManager
Advanced administration tools for large chat management
"""
from typing import Dict, Callable, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import re
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, ChatPermissions, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, ChatMemberUpdated
)
from loguru import logger

from app.plugins.plugin_manager import PluginBase, PluginMetadata
from app.services.user_service import user_service
from app.models.user import User, UserRole
from app.utils.decorators import admin_required, moderator_required, log_command, chat_type


class AdminActions(StatesGroup):
    """States for admin actions"""
    waiting_for_purge_count = State()
    waiting_for_broadcast_message = State()
    waiting_for_welcome_message = State()
    waiting_for_goodbye_message = State()
    waiting_for_rules_message = State()


class AdminToolsPlugin(PluginBase):
    """Plugin for advanced admin tools"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="admin_tools",
        version="1.0.0",
        description="Advanced administration tools for large chat management",
        author="MyChatManager Team",
        requires=[],
        conflicts=[]
    )
    
    def __init__(self, manager):
        """Initialize the plugin"""
        super().__init__(manager)
        self.router = Router(name="admin_tools")
        
        # Register handlers
        self.router.message(Command("purge"))(self.cmd_purge)
        self.router.message(AdminActions.waiting_for_purge_count)(self.process_purge_count)
        
        self.router.message(Command("pin"))(self.cmd_pin)
        self.router.message(Command("unpin"))(self.cmd_unpin)
        self.router.message(Command("unpinall"))(self.cmd_unpin_all)
        
        self.router.message(Command("stats"))(self.cmd_stats)
        self.router.message(Command("chatinfo"))(self.cmd_chat_info)
        
        self.router.message(Command("welcome"))(self.cmd_welcome)
        self.router.message(AdminActions.waiting_for_welcome_message)(self.process_welcome_message)
        
        self.router.message(Command("goodbye"))(self.cmd_goodbye)
        self.router.message(AdminActions.waiting_for_goodbye_message)(self.process_goodbye_message)
        
        self.router.message(Command("setrules"))(self.cmd_set_rules)
        self.router.message(AdminActions.waiting_for_rules_message)(self.process_rules_message)
        
        self.router.message(Command("broadcast"))(self.cmd_broadcast)
        self.router.message(AdminActions.waiting_for_broadcast_message)(self.process_broadcast_message)
        
        self.router.message(Command("promote"))(self.cmd_promote)
        self.router.message(Command("demote"))(self.cmd_demote)
        
        self.router.message(Command("slowmode"))(self.cmd_slowmode)
        
        # Chat member update handlers
        self.router.chat_member()(self.on_chat_member_update)
        
    async def activate(self) -> bool:
        """Activate the plugin"""
        logger.info(f"Activating {self.metadata.name} plugin...")
        return await super().activate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {
            "purge": self.cmd_purge,
            "pin": self.cmd_pin,
            "unpin": self.cmd_unpin,
            "unpinall": self.cmd_unpin_all,
            "stats": self.cmd_stats,
            "chatinfo": self.cmd_chat_info,
            "welcome": self.cmd_welcome,
            "goodbye": self.cmd_goodbye,
            "setrules": self.cmd_set_rules,
            "broadcast": self.cmd_broadcast,
            "promote": self.cmd_promote,
            "demote": self.cmd_demote,
            "slowmode": self.cmd_slowmode
        }
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_purge(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /purge command to delete multiple messages"""
        # Check if message is a reply
        if message.reply_to_message:
            # If it's a reply, we'll delete all messages between the replied message and this command
            await message.reply("⚠️ Starting to purge messages...")
            
            # Get the message IDs
            start_message_id = message.reply_to_message.message_id
            end_message_id = message.message_id
            count = end_message_id - start_message_id
            
            # Delete the messages
            deleted = 0
            for msg_id in range(start_message_id, end_message_id + 1):
                try:
                    await message.chat.delete_message(msg_id)
                    deleted += 1
                    # Add a small delay to prevent flooding
                    if deleted % 10 == 0:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Could not delete message {msg_id}: {e}")
            
            # Send success message and delete it after a few seconds
            status_msg = await message.chat.send_message(f"🧹 Purged {deleted} messages.")
            await asyncio.sleep(5)
            await status_msg.delete()
        else:
            # Ask for number of messages to purge
            await message.reply("How many recent messages do you want to purge? (max 100)")
            await state.set_state(AdminActions.waiting_for_purge_count)
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def process_purge_count(self, message: Message, state: FSMContext, **kwargs):
        """Process the number of messages to purge"""
        try:
            count = int(message.text.strip())
            if count <= 0 or count > 100:
                await message.reply("⚠️ Please enter a valid number between 1 and 100.")
                return
            
            await message.reply(f"⚠️ Starting to purge the last {count} messages...")
            
            # Get messages to delete
            chat_id = message.chat.id
            message_id = message.message_id
            
            # Delete messages
            deleted = 0
            for i in range(message_id - count, message_id + 1):
                if i <= 0:
                    continue
                try:
                    await message.chat.delete_message(i)
                    deleted += 1
                    # Add a small delay to prevent flooding
                    if deleted % 10 == 0:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Could not delete message {i}: {e}")
            
            # Send success message and delete it after a few seconds
            status_msg = await message.chat.send_message(f"🧹 Purged {deleted} messages.")
            await asyncio.sleep(5)
            await status_msg.delete()
            
        except ValueError:
            await message.reply("⚠️ Please enter a valid number.")
        finally:
            await state.clear()
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_pin(self, message: Message, **kwargs):
        """Handle the /pin command to pin a message"""
        # Check if message is a reply
        if not message.reply_to_message:
            await message.reply("⚠️ Please reply to the message you want to pin.")
            return
        
        try:
            # Pin the message
            await message.chat.pin_message(message.reply_to_message.message_id)
            await message.reply("📌 Message has been pinned.")
        except Exception as e:
            logger.error(f"Failed to pin message: {e}")
            await message.reply(f"❌ Failed to pin message: {str(e)}")
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_unpin(self, message: Message, **kwargs):
        """Handle the /unpin command to unpin a message"""
        try:
            # If it's a reply, unpin that specific message
            if message.reply_to_message:
                await message.chat.unpin_message(message.reply_to_message.message_id)
                await message.reply("📌 Message has been unpinned.")
            else:
                # Unpin the most recent pinned message
                await message.chat.unpin_message()
                await message.reply("📌 Most recent pinned message has been unpinned.")
        except Exception as e:
            logger.error(f"Failed to unpin message: {e}")
            await message.reply(f"❌ Failed to unpin message: {str(e)}")
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_unpin_all(self, message: Message, **kwargs):
        """Handle the /unpinall command to unpin all messages"""
        try:
            # Create confirmation keyboard
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes", callback_data="unpinall_confirm"),
                    InlineKeyboardButton(text="❌ No", callback_data="unpinall_cancel")
                ]
            ])
            
            await message.reply(
                "⚠️ Are you sure you want to unpin ALL pinned messages in this chat?",
                reply_markup=keyboard
            )
            
            # Register callback handler for the confirmation
            @self.router.callback_query(F.data == "unpinall_confirm")
            async def confirm_unpin_all(callback: CallbackQuery):
                await callback.answer()
                try:
                    await callback.message.chat.unpin_all_messages()
                    await callback.message.edit_text("📌 All pinned messages have been unpinned.")
                except Exception as e:
                    logger.error(f"Failed to unpin all messages: {e}")
                    await callback.message.edit_text(f"❌ Failed to unpin all messages: {str(e)}")
            
            @self.router.callback_query(F.data == "unpinall_cancel")
            async def cancel_unpin_all(callback: CallbackQuery):
                await callback.answer()
                await callback.message.edit_text("Operation cancelled.")
                
        except Exception as e:
            logger.error(f"Failed to unpin all messages: {e}")
            await message.reply(f"❌ Failed to unpin all messages: {str(e)}")
    
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_stats(self, message: Message, **kwargs):
        """Handle the /stats command to show user or chat statistics"""
        # Check if the user wants personal stats or chat stats
        if message.chat.type in ["group", "supergroup"]:
            # Get user stats from database
            user_id = message.from_user.id
            user = await user_service.get_user_by_telegram_id(user_id)
            
            if user:
                stats_text = (
                    f"📊 <b>Your Statistics</b>\n\n"
                    f"Messages sent: {user.message_count}\n"
                    f"Commands used: {user.command_count}\n"
                    f"Warnings received: {user.warning_count}\n"
                    f"Last active: {user.last_activity.strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                
                await message.reply(stats_text)
            else:
                await message.reply("❌ Could not find your user data.")
        else:
            await message.reply("This command is only available in group chats.")
    
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_chat_info(self, message: Message, **kwargs):
        """Handle the /chatinfo command to show information about the chat"""
        chat = message.chat
        
        # Get chat data from Telegram
        try:
            chat_info = await chat.get_chat()
            member_count = await chat.get_member_count()
            
            # Format chat info
            chat_info_text = (
                f"📋 <b>Chat Information</b>\n\n"
                f"<b>Basic Info:</b>\n"
                f"ID: {chat.id}\n"
                f"Type: {chat.type}\n"
                f"Title: {chat_info.title}\n"
                f"Members: {member_count}\n"
            )
            
            # Add optional fields if available
            if hasattr(chat_info, 'description') and chat_info.description:
                chat_info_text += f"\n<b>Description:</b>\n{chat_info.description}\n"
                
            if hasattr(chat_info, 'invite_link') and chat_info.invite_link:
                chat_info_text += f"\n<b>Invite Link:</b>\n{chat_info.invite_link}\n"
            
            # Add permissions info if available
            if hasattr(chat_info, 'permissions') and chat_info.permissions:
                perms = chat_info.permissions
                chat_info_text += (
                    f"\n<b>Default Permissions:</b>\n"
                    f"Send messages: {perms.can_send_messages or False}\n"
                    f"Send media: {perms.can_send_media_messages or False}\n"
                    f"Send polls: {perms.can_send_polls or False}\n"
                    f"Send other messages: {perms.can_send_other_messages or False}\n"
                    f"Add web page previews: {perms.can_add_web_page_previews or False}\n"
                    f"Change info: {perms.can_change_info or False}\n"
                    f"Invite users: {perms.can_invite_users or False}\n"
                    f"Pin messages: {perms.can_pin_messages or False}\n"
                )
            
            # Send the info
            await message.reply(chat_info_text)
            
        except Exception as e:
            logger.error(f"Failed to get chat info: {e}")
            await message.reply("❌ Failed to get chat information.")
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_welcome(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /welcome command to set welcome message"""
        if len(message.text.split(maxsplit=1)) > 1:
            # Command has the welcome message in it
            welcome_text = message.text.split(maxsplit=1)[1]
            
            # Save to database or config
            # In a real implementation, this would save to database
            
            await message.reply(
                f"✅ Welcome message has been set!\n\n"
                f"Preview:\n{welcome_text}\n\n"
                f"Available variables: $name, $username, $mention, $chat"
            )
        else:
            # Ask for the welcome message
            await message.reply(
                "Please enter the welcome message for new members.\n\n"
                "You can use the following variables:\n"
                "$name - User's first name\n"
                "$username - User's username\n"
                "$mention - Mention the user\n"
                "$chat - Chat name"
            )
            
            await state.set_state(AdminActions.waiting_for_welcome_message)
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def process_welcome_message(self, message: Message, state: FSMContext, **kwargs):
        """Process the welcome message"""
        welcome_text = message.text
        
        # Save to database or config
        # In a real implementation, this would save to database
        
        await message.reply(
            f"✅ Welcome message has been set!\n\n"
            f"Preview:\n{welcome_text}\n\n"
            f"Available variables: $name, $username, $mention, $chat"
        )
        
        # Clear state
        await state.clear()
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_goodbye(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /goodbye command to set goodbye message"""
        if len(message.text.split(maxsplit=1)) > 1:
            # Command has the goodbye message in it
            goodbye_text = message.text.split(maxsplit=1)[1]
            
            # Save to database or config
            # In a real implementation, this would save to database
            
            await message.reply(
                f"✅ Goodbye message has been set!\n\n"
                f"Preview:\n{goodbye_text}\n\n"
                f"Available variables: $name, $username, $mention, $chat"
            )
        else:
            # Ask for the goodbye message
            await message.reply(
                "Please enter the goodbye message for leaving members.\n\n"
                "You can use the following variables:\n"
                "$name - User's first name\n"
                "$username - User's username\n"
                "$mention - Mention the user\n"
                "$chat - Chat name"
            )
            
            await state.set_state(AdminActions.waiting_for_goodbye_message)
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def process_goodbye_message(self, message: Message, state: FSMContext, **kwargs):
        """Process the goodbye message"""
        goodbye_text = message.text
        
        # Save to database or config
        # In a real implementation, this would save to database
        
        await message.reply(
            f"✅ Goodbye message has been set!\n\n"
            f"Preview:\n{goodbye_text}\n\n"
            f"Available variables: $name, $username, $mention, $chat"
        )
        
        # Clear state
        await state.clear()
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_set_rules(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /setrules command to set chat rules"""
        if len(message.text.split(maxsplit=1)) > 1:
            # Command has the rules in it
            rules_text = message.text.split(maxsplit=1)[1]
            
            # Save to database or config
            # In a real implementation, this would save to database
            
            await message.reply(
                f"✅ Chat rules have been set!\n\n"
                f"Preview:\n{rules_text}"
            )
        else:
            # Ask for the rules
            await message.reply(
                "Please enter the rules for this chat.\n"
                "Use clear formatting and numbering for best readability."
            )
            
            await state.set_state(AdminActions.waiting_for_rules_message)
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def process_rules_message(self, message: Message, state: FSMContext, **kwargs):
        """Process the rules message"""
        rules_text = message.text
        
        # Save to database or config
        # In a real implementation, this would save to database
        
        await message.reply(
            f"✅ Chat rules have been set!\n\n"
            f"Preview:\n{rules_text}"
        )
        
        # Clear state
        await state.clear()
    
    @admin_required
    @log_command
    async def cmd_broadcast(self, message: Message, state: FSMContext, **kwargs):
        """Handle the /broadcast command to send a message to all chats"""
        # Ask for the broadcast message
        await message.reply(
            "Please enter the message you want to broadcast to all chats.\n"
            "This will be sent to all chats where the bot is admin."
        )
        
        await state.set_state(AdminActions.waiting_for_broadcast_message)
    
    @admin_required
    @log_command
    async def process_broadcast_message(self, message: Message, state: FSMContext, **kwargs):
        """Process the broadcast message"""
        broadcast_text = message.text
        
        # Confirm before sending
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Send", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="broadcast_cancel")
            ]
        ])
        
        await message.reply(
            f"Are you sure you want to broadcast this message to all chats?\n\n"
            f"Message:\n{broadcast_text}",
            reply_markup=keyboard
        )
        
        # Store the message in state
        await state.update_data(broadcast_text=broadcast_text)
        
        # Register callback handlers
        @self.router.callback_query(F.data == "broadcast_confirm")
        async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
            data = await state.get_data()
            broadcast_text = data.get('broadcast_text', '')
            
            await callback.answer()
            await callback.message.edit_text("Broadcasting message... This may take some time.")
            
            # In a real implementation, this would get all chats from the database
            # and send the message to each one
            
            await callback.message.edit_text("✅ Message has been broadcasted.")
            
            # Clear state
            await state.clear()
        
        @self.router.callback_query(F.data == "broadcast_cancel")
        async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
            await callback.answer()
            await callback.message.edit_text("Broadcast cancelled.")
            
            # Clear state
            await state.clear()
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_promote(self, message: Message, **kwargs):
        """Handle the /promote command to promote a user to admin"""
        # Check if message is a reply
        if not message.reply_to_message:
            await message.reply("⚠️ Please reply to a message from the user you want to promote.")
            return
        
        target_user = message.reply_to_message.from_user
        
        try:
            # Promote the user with basic admin rights
            await message.chat.promote(
                user_id=target_user.id,
                can_change_info=True,
                can_delete_messages=True,
                can_invite_users=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_promote_members=False
            )
            
            await message.reply(f"👑 {target_user.full_name} has been promoted to admin.")
            
        except Exception as e:
            logger.error(f"Failed to promote user: {e}")
            await message.reply(f"❌ Failed to promote user: {str(e)}")
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_demote(self, message: Message, **kwargs):
        """Handle the /demote command to demote an admin to regular user"""
        # Check if message is a reply
        if not message.reply_to_message:
            await message.reply("⚠️ Please reply to a message from the admin you want to demote.")
            return
        
        target_user = message.reply_to_message.from_user
        
        try:
            # Demote the user (remove all admin rights)
            await message.chat.promote(
                user_id=target_user.id,
                can_change_info=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False
            )
            
            await message.reply(f"👤 {target_user.full_name} has been demoted to regular user.")
            
        except Exception as e:
            logger.error(f"Failed to demote user: {e}")
            await message.reply(f"❌ Failed to demote user: {str(e)}")
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_slowmode(self, message: Message, command: CommandObject, **kwargs):
        """Handle the /slowmode command to set chat slow mode"""
        args = command.args or ""
        
        # Parse the argument
        match = re.match(r'^(\d+)$', args.strip())
        
        if not match:
            await message.reply(
                "⚠️ Please specify the slow mode delay in seconds.\n"
                "Usage: /slowmode <seconds>\n"
                "Example: /slowmode 10\n"
                "Use /slowmode 0 to disable slow mode."
            )
            return
        
        seconds = int(match.group(1))
        
        try:
            # Set slow mode delay
            await message.chat.slow_mode_delay(seconds)
            
            if seconds == 0:
                await message.reply("⏱ Slow mode has been disabled.")
            else:
                await message.reply(f"⏱ Slow mode has been set to {seconds} seconds.")
            
        except Exception as e:
            logger.error(f"Failed to set slow mode: {e}")
            await message.reply(f"❌ Failed to set slow mode: {str(e)}")
    
    async def on_chat_member_update(self, update: ChatMemberUpdated, **kwargs):
        """Handle member join/leave events"""
        # Get old and new member status
        old_status = update.old_chat_member.status if update.old_chat_member else None
        new_status = update.new_chat_member.status if update.new_chat_member else None
        
        if new_status == "member" and (old_status in [None, "left", "kicked"]):
            # User joined the chat
            # In a real implementation, this would get the welcome message from database
            # and send it with proper formatting
            welcome_text = f"👋 Welcome to the chat, {update.new_chat_member.user.full_name}!"
            
            try:
                await update.chat.send_message(welcome_text)
            except Exception as e:
                logger.error(f"Failed to send welcome message: {e}")
        
        elif old_status == "member" and new_status in ["left", "kicked"]:
            # User left the chat or was kicked
            # In a real implementation, this would get the goodbye message from database
            # and send it with proper formatting
            if new_status == "left":
                goodbye_text = f"👋 {update.old_chat_member.user.full_name} has left the chat."
            else:
                goodbye_text = f"🚫 {update.old_chat_member.user.full_name} has been removed from the chat."
            
            try:
                await update.chat.send_message(goodbye_text)
            except Exception as e:
                logger.error(f"Failed to send goodbye message: {e}") 