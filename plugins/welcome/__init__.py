"""
Welcome Plugin for MyChatManager
Show welcome messages for new users and goodbye messages for users who leave
"""
from typing import Dict, Callable, Any, List, Optional
import asyncio
from datetime import datetime
from aiogram import Router, F, html
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

from app.plugins.plugin_manager import PluginBase, PluginMetadata
from app.services.user_service import user_service
from app.models.user import User, UserRole
from app.utils.decorators import admin_required, moderator_required, log_command, chat_type


class WelcomeStates(StatesGroup):
    """States for setting welcome/goodbye messages"""
    set_welcome = State()
    set_goodbye = State()
    set_rules = State()


class WelcomePlugin(PluginBase):
    """Plugin for welcoming new users and farewell for those who leave"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="welcome",
        version="1.0.0",
        description="Welcome new users and say goodbye to those who leave",
        author="MyChatManager Team",
        requires=[],
        conflicts=[]
    )
    
    def __init__(self, manager):
        """Initialize the plugin"""
        super().__init__(manager)
        self.router = Router(name="welcome")
        
        # In-memory storage for welcome/goodbye messages
        # {chat_id: {"welcome": "welcome_message", "goodbye": "goodbye_message", "rules": "rules_text"}}
        self.messages = {}
        
        # Default messages
        self.default_welcome = "👋 Welcome {mention} to {chat_title}!"
        self.default_goodbye = "👋 {user_name} has left the chat. Goodbye!"
        
        # Register handlers
        self.router.message(Command("welcome"))(self.cmd_welcome)
        self.router.message(Command("goodbye"))(self.cmd_goodbye)
        self.router.message(Command("setwelcome"))(self.cmd_set_welcome)
        self.router.message(Command("setgoodbye"))(self.cmd_set_goodbye)
        self.router.message(Command("resetwelcome"))(self.cmd_reset_welcome)
        self.router.message(Command("resetgoodbye"))(self.cmd_reset_goodbye)
        self.router.message(Command("rules"))(self.cmd_rules)
        self.router.message(Command("setrules"))(self.cmd_set_rules)
        
        # Register callback query handlers
        self.router.callback_query(F.data.startswith("welcome_"))(self.handle_welcome_callback)
        
        # Register chat member updated handlers
        self.router.chat_member(
            ChatMemberUpdatedFilter(member_status_changed=True)
        )(self.on_chat_member_updated)
        
        # Register state handlers
        self.router.message(WelcomeStates.set_welcome)(self.handle_set_welcome)
        self.router.message(WelcomeStates.set_goodbye)(self.handle_set_goodbye)
        self.router.message(WelcomeStates.set_rules)(self.handle_set_rules)
    
    async def activate(self) -> bool:
        """Activate the plugin"""
        logger.info(f"Activating {self.metadata.name} plugin...")
        return await super().activate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {
            "welcome": self.cmd_welcome,
            "goodbye": self.cmd_goodbye,
            "setwelcome": self.cmd_set_welcome,
            "setgoodbye": self.cmd_set_goodbye,
            "resetwelcome": self.cmd_reset_welcome,
            "resetgoodbye": self.cmd_reset_goodbye,
            "rules": self.cmd_rules,
            "setrules": self.cmd_set_rules
        }
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_welcome(self, message: Message, **kwargs):
        """Show current welcome message"""
        chat_id = message.chat.id
        
        # Get welcome message for this chat
        welcome_message = self.get_welcome_message(chat_id)
        
        # Replace placeholders with actual values for preview
        preview = welcome_message.format(
            mention=f"@{message.from_user.username or message.from_user.id}",
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Set new welcome message",
                    callback_data="welcome_set"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Reset to default",
                    callback_data="welcome_reset"
                )
            ]
        ])
        
        await message.reply(
            f"📋 <b>Current welcome message:</b>\n\n{preview}\n\n"
            f"<b>Available placeholders:</b>\n"
            f"{{mention}} - User mention\n"
            f"{{user_name}} - User's name\n"
            f"{{chat_title}} - Chat title\n"
            f"{{id}} - User's ID",
            reply_markup=buttons
        )
    
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_goodbye(self, message: Message, **kwargs):
        """Show current goodbye message"""
        chat_id = message.chat.id
        
        # Get goodbye message for this chat
        goodbye_message = self.get_goodbye_message(chat_id)
        
        # Replace placeholders with actual values for preview
        preview = goodbye_message.format(
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Set new goodbye message",
                    callback_data="welcome_setgoodbye"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Reset to default",
                    callback_data="welcome_resetgoodbye"
                )
            ]
        ])
        
        await message.reply(
            f"📋 <b>Current goodbye message:</b>\n\n{preview}\n\n"
            f"<b>Available placeholders:</b>\n"
            f"{{user_name}} - User's name\n"
            f"{{chat_title}} - Chat title\n"
            f"{{id}} - User's ID",
            reply_markup=buttons
        )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_set_welcome(self, message: Message, command: CommandObject, state: FSMContext, **kwargs):
        """Set welcome message for the chat"""
        chat_id = message.chat.id
        
        if command.args:
            # Set welcome message from command
            new_welcome = command.args
            await self.update_welcome_message(chat_id, new_welcome)
            
            # Show preview
            preview = new_welcome.format(
                mention=f"@{message.from_user.username or message.from_user.id}",
                user_name=message.from_user.full_name,
                chat_title=message.chat.title,
                id=message.from_user.id
            )
            
            await message.reply(
                f"✅ Welcome message updated!\n\n"
                f"<b>Preview:</b>\n{preview}"
            )
            
        else:
            # Ask for welcome message
            await state.set_state(WelcomeStates.set_welcome)
            await message.reply(
                "📝 Please send the new welcome message.\n\n"
                "<b>Available placeholders:</b>\n"
                "{mention} - User mention\n"
                "{user_name} - User's name\n"
                "{chat_title} - Chat title\n"
                "{id} - User's ID\n\n"
                "Send /cancel to cancel."
            )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_set_goodbye(self, message: Message, command: CommandObject, state: FSMContext, **kwargs):
        """Set goodbye message for the chat"""
        chat_id = message.chat.id
        
        if command.args:
            # Set goodbye message from command
            new_goodbye = command.args
            await self.update_goodbye_message(chat_id, new_goodbye)
            
            # Show preview
            preview = new_goodbye.format(
                user_name=message.from_user.full_name,
                chat_title=message.chat.title,
                id=message.from_user.id
            )
            
            await message.reply(
                f"✅ Goodbye message updated!\n\n"
                f"<b>Preview:</b>\n{preview}"
            )
            
        else:
            # Ask for goodbye message
            await state.set_state(WelcomeStates.set_goodbye)
            await message.reply(
                "📝 Please send the new goodbye message.\n\n"
                "<b>Available placeholders:</b>\n"
                "{user_name} - User's name\n"
                "{chat_title} - Chat title\n"
                "{id} - User's ID\n\n"
                "Send /cancel to cancel."
            )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_reset_welcome(self, message: Message, **kwargs):
        """Reset welcome message to default"""
        chat_id = message.chat.id
        
        # Initialize chat if not exists
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        
        # Reset welcome message
        if "welcome" in self.messages[chat_id]:
            del self.messages[chat_id]["welcome"]
        
        # Show default message
        welcome_message = self.get_welcome_message(chat_id)
        preview = welcome_message.format(
            mention=f"@{message.from_user.username or message.from_user.id}",
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        await message.reply(
            f"✅ Welcome message has been reset to default.\n\n"
            f"<b>Preview:</b>\n{preview}"
        )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_reset_goodbye(self, message: Message, **kwargs):
        """Reset goodbye message to default"""
        chat_id = message.chat.id
        
        # Initialize chat if not exists
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        
        # Reset goodbye message
        if "goodbye" in self.messages[chat_id]:
            del self.messages[chat_id]["goodbye"]
        
        # Show default message
        goodbye_message = self.get_goodbye_message(chat_id)
        preview = goodbye_message.format(
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        await message.reply(
            f"✅ Goodbye message has been reset to default.\n\n"
            f"<b>Preview:</b>\n{preview}"
        )
    
    @log_command
    @chat_type("group", "supergroup", "private")
    async def cmd_rules(self, message: Message, **kwargs):
        """Show chat rules"""
        chat_id = message.chat.id
        
        # Get rules for this chat
        rules = self.get_chat_rules(chat_id)
        
        if not rules:
            # No rules set
            if message.chat.type == "private":
                await message.reply(
                    "❌ You need to specify a chat to view rules from.\n"
                    "Use /rules chat_id"
                )
            else:
                buttons = None
                if await self.check_user_is_admin(message.chat.id, message.from_user.id):
                    buttons = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📝 Set rules",
                                callback_data="welcome_setrules"
                            )
                        ]
                    ])
                
                await message.reply(
                    "❌ No rules have been set for this chat yet.",
                    reply_markup=buttons
                )
        else:
            # Show rules
            if message.chat.type == "private":
                await message.reply(
                    f"📋 <b>Rules for {message.chat.title}:</b>\n\n{rules}"
                )
            else:
                buttons = None
                if await self.check_user_is_admin(message.chat.id, message.from_user.id):
                    buttons = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📝 Update rules",
                                callback_data="welcome_setrules"
                            )
                        ]
                    ])
                
                await message.reply(
                    f"📋 <b>Chat Rules:</b>\n\n{rules}",
                    reply_markup=buttons
                )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_set_rules(self, message: Message, command: CommandObject, state: FSMContext, **kwargs):
        """Set rules for the chat"""
        chat_id = message.chat.id
        
        if command.args:
            # Set rules from command
            new_rules = command.args
            await self.update_chat_rules(chat_id, new_rules)
            
            await message.reply(
                f"✅ Chat rules have been updated!\n\n"
                f"Users can view them with /rules"
            )
            
        else:
            # Ask for rules
            await state.set_state(WelcomeStates.set_rules)
            await message.reply(
                "📝 Please send the new chat rules.\n\n"
                "Send /cancel to cancel."
            )
    
    async def handle_set_welcome(self, message: Message, state: FSMContext, **kwargs):
        """Handle setting welcome message in state"""
        # Cancel if command
        if message.is_command():
            if message.text.startswith("/cancel"):
                await state.clear()
                await message.reply("Operation cancelled.")
                return
            
            # Continue with other commands
            return
        
        chat_id = message.chat.id
        new_welcome = message.text
        
        # Update welcome message
        await self.update_welcome_message(chat_id, new_welcome)
        
        # Clear state
        await state.clear()
        
        # Show preview
        preview = new_welcome.format(
            mention=f"@{message.from_user.username or message.from_user.id}",
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        await message.reply(
            f"✅ Welcome message updated!\n\n"
            f"<b>Preview:</b>\n{preview}"
        )
    
    async def handle_set_goodbye(self, message: Message, state: FSMContext, **kwargs):
        """Handle setting goodbye message in state"""
        # Cancel if command
        if message.is_command():
            if message.text.startswith("/cancel"):
                await state.clear()
                await message.reply("Operation cancelled.")
                return
            
            # Continue with other commands
            return
        
        chat_id = message.chat.id
        new_goodbye = message.text
        
        # Update goodbye message
        await self.update_goodbye_message(chat_id, new_goodbye)
        
        # Clear state
        await state.clear()
        
        # Show preview
        preview = new_goodbye.format(
            user_name=message.from_user.full_name,
            chat_title=message.chat.title,
            id=message.from_user.id
        )
        
        await message.reply(
            f"✅ Goodbye message updated!\n\n"
            f"<b>Preview:</b>\n{preview}"
        )
    
    async def handle_set_rules(self, message: Message, state: FSMContext, **kwargs):
        """Handle setting rules in state"""
        # Cancel if command
        if message.is_command():
            if message.text.startswith("/cancel"):
                await state.clear()
                await message.reply("Operation cancelled.")
                return
            
            # Continue with other commands
            return
        
        chat_id = message.chat.id
        new_rules = message.text
        
        # Update rules
        await self.update_chat_rules(chat_id, new_rules)
        
        # Clear state
        await state.clear()
        
        await message.reply(
            f"✅ Chat rules have been updated!\n\n"
            f"Users can view them with /rules"
        )
    
    async def handle_welcome_callback(self, callback_query: CallbackQuery, state: FSMContext, **kwargs):
        """Handle callback queries for welcome plugin"""
        await callback_query.answer()
        
        chat_id = callback_query.message.chat.id
        data = callback_query.data
        
        if data == "welcome_set":
            # Set welcome message
            await state.set_state(WelcomeStates.set_welcome)
            await callback_query.message.reply(
                "📝 Please send the new welcome message.\n\n"
                "<b>Available placeholders:</b>\n"
                "{mention} - User mention\n"
                "{user_name} - User's name\n"
                "{chat_title} - Chat title\n"
                "{id} - User's ID\n\n"
                "Send /cancel to cancel."
            )
            
        elif data == "welcome_reset":
            # Reset welcome message
            if chat_id in self.messages and "welcome" in self.messages[chat_id]:
                del self.messages[chat_id]["welcome"]
            
            # Show default message
            welcome_message = self.get_welcome_message(chat_id)
            preview = welcome_message.format(
                mention=f"@{callback_query.from_user.username or callback_query.from_user.id}",
                user_name=callback_query.from_user.full_name,
                chat_title=callback_query.message.chat.title,
                id=callback_query.from_user.id
            )
            
            await callback_query.message.edit_text(
                f"✅ Welcome message has been reset to default.\n\n"
                f"<b>Preview:</b>\n{preview}"
            )
            
        elif data == "welcome_setgoodbye":
            # Set goodbye message
            await state.set_state(WelcomeStates.set_goodbye)
            await callback_query.message.reply(
                "📝 Please send the new goodbye message.\n\n"
                "<b>Available placeholders:</b>\n"
                "{user_name} - User's name\n"
                "{chat_title} - Chat title\n"
                "{id} - User's ID\n\n"
                "Send /cancel to cancel."
            )
            
        elif data == "welcome_resetgoodbye":
            # Reset goodbye message
            if chat_id in self.messages and "goodbye" in self.messages[chat_id]:
                del self.messages[chat_id]["goodbye"]
            
            # Show default message
            goodbye_message = self.get_goodbye_message(chat_id)
            preview = goodbye_message.format(
                user_name=callback_query.from_user.full_name,
                chat_title=callback_query.message.chat.title,
                id=callback_query.from_user.id
            )
            
            await callback_query.message.edit_text(
                f"✅ Goodbye message has been reset to default.\n\n"
                f"<b>Preview:</b>\n{preview}"
            )
            
        elif data == "welcome_setrules":
            # Set rules
            await state.set_state(WelcomeStates.set_rules)
            await callback_query.message.reply(
                "📝 Please send the new chat rules.\n\n"
                "Send /cancel to cancel."
            )
    
    async def on_chat_member_updated(self, update: ChatMemberUpdated, **kwargs):
        """Handle chat member updates (joins/leaves)"""
        # Skip updates without user info
        if not update.from_user or not update.chat:
            return
        
        # Skip service updates
        if update.from_user.is_bot or update.chat.type not in ["group", "supergroup"]:
            return
        
        old_status = update.old_chat_member.status if update.old_chat_member else None
        new_status = update.new_chat_member.status if update.new_chat_member else None
        
        # Handle user join
        if (old_status in [None, "left", "kicked"] and 
            new_status in ["member", "administrator", "creator"]):
            await self.send_welcome_message(update)
        
        # Handle user leave
        elif (old_status in ["member", "administrator", "creator"] and 
              new_status in [None, "left", "kicked"]):
            await self.send_goodbye_message(update)
    
    async def send_welcome_message(self, update: ChatMemberUpdated):
        """Send welcome message to new chat member"""
        chat_id = update.chat.id
        user = update.from_user
        
        # Get welcome message for this chat
        welcome_message = self.get_welcome_message(chat_id)
        
        # Check if there are rules
        has_rules = self.get_chat_rules(chat_id) is not None
        rules_button = None
        
        if has_rules:
            # Create rules button
            rules_button = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 Read the rules",
                        callback_data="welcome_showrules"
                    )
                ]
            ])
        
        # Replace placeholders
        message = welcome_message.format(
            mention=f"@{user.username}" if user.username else user.full_name,
            user_name=user.full_name,
            chat_title=update.chat.title,
            id=user.id
        )
        
        # Send welcome message
        try:
            await update.chat.send_message(
                message,
                reply_markup=rules_button
            )
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
    
    async def send_goodbye_message(self, update: ChatMemberUpdated):
        """Send goodbye message when user leaves chat"""
        chat_id = update.chat.id
        user = update.from_user
        
        # Get goodbye message for this chat
        goodbye_message = self.get_goodbye_message(chat_id)
        
        # Replace placeholders
        message = goodbye_message.format(
            user_name=user.full_name,
            chat_title=update.chat.title,
            id=user.id
        )
        
        # Send goodbye message
        try:
            await update.chat.send_message(message)
        except Exception as e:
            logger.error(f"Error sending goodbye message: {e}")
    
    def get_welcome_message(self, chat_id: int) -> str:
        """Get welcome message for a chat"""
        if chat_id in self.messages and "welcome" in self.messages[chat_id]:
            return self.messages[chat_id]["welcome"]
        return self.default_welcome
    
    def get_goodbye_message(self, chat_id: int) -> str:
        """Get goodbye message for a chat"""
        if chat_id in self.messages and "goodbye" in self.messages[chat_id]:
            return self.messages[chat_id]["goodbye"]
        return self.default_goodbye
    
    def get_chat_rules(self, chat_id: int) -> Optional[str]:
        """Get rules for a chat"""
        if chat_id in self.messages and "rules" in self.messages[chat_id]:
            return self.messages[chat_id]["rules"]
        return None
    
    async def update_welcome_message(self, chat_id: int, message: str):
        """Update welcome message for a chat"""
        # Initialize chat if not exists
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        
        # Update welcome message
        self.messages[chat_id]["welcome"] = message
    
    async def update_goodbye_message(self, chat_id: int, message: str):
        """Update goodbye message for a chat"""
        # Initialize chat if not exists
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        
        # Update goodbye message
        self.messages[chat_id]["goodbye"] = message
    
    async def update_chat_rules(self, chat_id: int, rules: str):
        """Update rules for a chat"""
        # Initialize chat if not exists
        if chat_id not in self.messages:
            self.messages[chat_id] = {}
        
        # Update rules
        self.messages[chat_id]["rules"] = rules
    
    async def check_user_is_admin(self, chat_id: int, user_id: int) -> bool:
        """Check if user is an admin"""
        try:
            chat_member = await self.bot.get_chat_member(chat_id, user_id)
            return chat_member.status in ["administrator", "creator"]
        except Exception:
            return False 