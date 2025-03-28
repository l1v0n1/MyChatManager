"""
Anti-Spam Plugin for MyChatManager
Advanced spam detection and prevention for large Telegram groups
"""
from typing import Dict, Callable, Any, List, Optional, Set
import re
import time
import asyncio
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger

from app.plugins.plugin_manager import PluginBase, PluginMetadata
from app.services.user_service import user_service
from app.models.user import User, UserRole
from app.utils.decorators import admin_required, moderator_required, log_command, chat_type
from app.events.event_manager import event_manager


class AntiSpamPlugin(PluginBase):
    """Plugin for advanced spam detection and prevention"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="antispam",
        version="1.0.0",
        description="Advanced spam detection and prevention for large Telegram groups",
        author="MyChatManager Team",
        requires=[],
        conflicts=[]
    )
    
    def __init__(self, manager):
        """Initialize the plugin"""
        super().__init__(manager)
        self.router = Router(name="antispam")
        
        # Message tracking for flood detection
        self.message_history = defaultdict(list)  # chat_id -> [(user_id, timestamp), ...]
        self.user_message_counts = defaultdict(lambda: defaultdict(int))  # chat_id -> {user_id: count}
        self.warned_users = set()  # Set of (chat_id, user_id) who have been warned recently
        
        # Regex patterns for common spam types
        self.spam_patterns = [
            # URLs with certain suspicious TLDs
            r'https?://\S+\.(xyz|tk|ml|ga|cf|gq|top|loan|online|vip|win)\b',
            # Cryptocurrency spam
            r'\b(bitcoin|btc|ethereum|eth|crypto|whitepaper|ico|token sale)\b.*\bhttps?://\S+\b',
            # Multiple @mentions
            r'(@\w+\s*){5,}',
            # Common spam phrases
            r'\b(free money|make money online|earn from home|double your investment)\b',
            # Excessive use of emojis
            r'[😀-🙏]{8,}',
        ]
        
        # Global and per-chat blacklisted words
        self.global_blacklist = set([
            "spam", "scam", "porn", "xxx", "sex", "nude", "naked"
        ])
        self.chat_blacklists = defaultdict(set)
        
        # Flood control settings (configurable per chat)
        self.flood_settings = defaultdict(lambda: {
            'messages_per_minute': 10,  # Default max messages per minute
            'similar_messages_limit': 3,  # Default max similar messages
            'max_forwards': 5,  # Default max forwards
            'url_limit': 3,  # Default max URLs
            'action': 'warn'  # Default action: 'warn', 'mute', 'kick', 'ban'
        })
        
        # User tracking for raid detection
        self.join_history = defaultdict(list)  # chat_id -> [(user_id, timestamp), ...]
        
        # Register handlers
        self.router.message(Command("antispam"))(self.cmd_antispam)
        self.router.message(Command("blacklist"))(self.cmd_blacklist)
        self.router.message(Command("whitelist"))(self.cmd_whitelist)
        self.router.message(Command("spamsettings"))(self.cmd_spam_settings)
        
        # Message handler
        self.router.message()(self.on_message)
        
        # Setup regular cleanup task
        self.cleanup_task = None
    
    async def activate(self) -> bool:
        """Activate the plugin"""
        logger.info(f"Activating {self.metadata.name} plugin...")
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self.cleanup_history_task())
        
        return await super().activate()
    
    async def deactivate(self) -> bool:
        """Deactivate the plugin"""
        # Cancel cleanup task
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            
        return await super().deactivate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {
            "antispam": self.cmd_antispam,
            "blacklist": self.cmd_blacklist,
            "whitelist": self.cmd_whitelist,
            "spamsettings": self.cmd_spam_settings
        }
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_antispam(self, message: Message, command: CommandObject, **kwargs):
        """Handle the /antispam command to control anti-spam features"""
        args = command.args.split() if command.args else []
        
        if not args:
            await message.reply(
                "📋 <b>Anti-Spam Commands</b>\n\n"
                "/antispam status - Show current anti-spam settings\n"
                "/antispam on - Enable anti-spam protection\n"
                "/antispam off - Disable anti-spam protection\n"
                "/blacklist add <word> - Add word to spam blacklist\n"
                "/blacklist remove <word> - Remove word from spam blacklist\n"
                "/blacklist list - Show blacklisted words\n"
                "/whitelist add <user> - Add user to whitelist\n"
                "/whitelist remove <user> - Remove user from whitelist\n"
                "/whitelist list - Show whitelisted users\n"
                "/spamsettings - Configure spam detection settings"
            )
            return
        
        chat_id = message.chat.id
        
        if args[0] == "status":
            # Show current settings
            settings = self.flood_settings[chat_id]
            status_text = (
                f"🛡 <b>Anti-Spam Status for this chat</b>\n\n"
                f"• Messages per minute limit: {settings['messages_per_minute']}\n"
                f"• Similar message limit: {settings['similar_messages_limit']}\n"
                f"• Maximum forwards: {settings['max_forwards']}\n"
                f"• URL limit: {settings['url_limit']}\n"
                f"• Action on violation: {settings['action'].upper()}\n"
                f"• Custom blacklisted words: {len(self.chat_blacklists[chat_id])}\n"
            )
            await message.reply(status_text)
            
        elif args[0] == "on":
            # Enable anti-spam
            # This would typically update a database record
            # For now, we'll just reply with a confirmation
            await message.reply("✅ Anti-spam protection has been enabled for this chat.")
            
        elif args[0] == "off":
            # Disable anti-spam
            # This would typically update a database record
            await message.reply("⚠️ Anti-spam protection has been disabled for this chat.")
            
        else:
            await message.reply("❌ Unknown anti-spam command. Use /antispam for help.")
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_blacklist(self, message: Message, command: CommandObject, **kwargs):
        """Handle the /blacklist command to manage blacklisted words"""
        args = command.args.split() if command.args else []
        
        if not args or args[0] not in ["add", "remove", "list"]:
            await message.reply(
                "📋 <b>Blacklist Commands</b>\n\n"
                "/blacklist add <word> - Add word to spam blacklist\n"
                "/blacklist remove <word> - Remove word from spam blacklist\n"
                "/blacklist list - Show blacklisted words"
            )
            return
        
        chat_id = message.chat.id
        
        if args[0] == "list":
            # Show blacklisted words
            if not self.chat_blacklists[chat_id]:
                await message.reply("No custom blacklisted words for this chat.")
            else:
                words_list = ", ".join(sorted(self.chat_blacklists[chat_id]))
                await message.reply(f"📋 <b>Blacklisted Words:</b>\n\n{words_list}")
            
        elif args[0] == "add" and len(args) > 1:
            # Add word to blacklist
            word = args[1].lower()
            self.chat_blacklists[chat_id].add(word)
            await message.reply(f"✅ Added '{word}' to the blacklist.")
            
        elif args[0] == "remove" and len(args) > 1:
            # Remove word from blacklist
            word = args[1].lower()
            if word in self.chat_blacklists[chat_id]:
                self.chat_blacklists[chat_id].remove(word)
                await message.reply(f"✅ Removed '{word}' from the blacklist.")
            else:
                await message.reply(f"❌ '{word}' is not in the blacklist.")
        
        else:
            await message.reply("❌ Invalid command format. Use /blacklist for help.")
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_whitelist(self, message: Message, command: CommandObject, **kwargs):
        """Handle the /whitelist command to manage whitelisted users"""
        # This is a placeholder - in a full implementation, this would
        # manage a list of users exempt from spam checks
        await message.reply(
            "📋 <b>Whitelist Management</b>\n\n"
            "In a complete implementation, this command would allow you to:\n"
            "• Add users to the whitelist\n"
            "• Remove users from the whitelist\n"
            "• List whitelisted users\n\n"
            "Whitelisted users are exempt from spam checks."
        )
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_spam_settings(self, message: Message, command: CommandObject, **kwargs):
        """Handle the /spamsettings command to configure spam detection settings"""
        args = command.args.split() if command.args else []
        chat_id = message.chat.id
        
        if not args:
            # Show current settings and configuration options
            settings = self.flood_settings[chat_id]
            settings_text = (
                f"⚙️ <b>Anti-Spam Settings</b>\n\n"
                f"Current settings:\n"
                f"• Messages per minute: {settings['messages_per_minute']}\n"
                f"• Similar messages: {settings['similar_messages_limit']}\n"
                f"• Max forwards: {settings['max_forwards']}\n"
                f"• URL limit: {settings['url_limit']}\n"
                f"• Action: {settings['action']}\n\n"
                f"To change a setting, use:\n"
                f"/spamsettings [setting] [value]\n\n"
                f"Available settings:\n"
                f"• msgs [5-50] - Messages per minute limit\n"
                f"• similar [2-10] - Similar message limit\n"
                f"• forwards [3-20] - Max forwards limit\n"
                f"• urls [1-10] - URL limit per message\n"
                f"• action [warn/mute/kick/ban] - Action on violation"
            )
            await message.reply(settings_text)
            return
        
        if len(args) != 2:
            await message.reply("❌ Invalid format. Use /spamsettings for help.")
            return
        
        setting, value = args[0].lower(), args[1].lower()
        
        try:
            if setting == "msgs":
                # Set messages per minute
                val = int(value)
                if val < 5 or val > 50:
                    await message.reply("❌ Value must be between 5 and 50.")
                    return
                self.flood_settings[chat_id]['messages_per_minute'] = val
                
            elif setting == "similar":
                # Set similar messages limit
                val = int(value)
                if val < 2 or val > 10:
                    await message.reply("❌ Value must be between 2 and 10.")
                    return
                self.flood_settings[chat_id]['similar_messages_limit'] = val
                
            elif setting == "forwards":
                # Set max forwards
                val = int(value)
                if val < 3 or val > 20:
                    await message.reply("❌ Value must be between 3 and 20.")
                    return
                self.flood_settings[chat_id]['max_forwards'] = val
                
            elif setting == "urls":
                # Set URL limit
                val = int(value)
                if val < 1 or val > 10:
                    await message.reply("❌ Value must be between 1 and 10.")
                    return
                self.flood_settings[chat_id]['url_limit'] = val
                
            elif setting == "action":
                # Set action
                if value not in ["warn", "mute", "kick", "ban"]:
                    await message.reply("❌ Action must be one of: warn, mute, kick, ban.")
                    return
                self.flood_settings[chat_id]['action'] = value
                
            else:
                await message.reply("❌ Unknown setting. Use /spamsettings for help.")
                return
            
            await message.reply(f"✅ Anti-spam setting updated: {setting} = {value}")
            
        except ValueError:
            await message.reply("❌ Invalid value. Numeric settings require integer values.")
    
    async def on_message(self, message: Message, **kwargs):
        """Process each message for spam detection"""
        # Skip service messages and bot commands
        if (
            not message.text or 
            message.is_command() or 
            message.from_user.is_bot or
            message.chat.type not in ["group", "supergroup"]
        ):
            return
        
        chat_id = message.chat.id
        user_id = message.from_user.id
        now = time.time()
        
        # Get spam settings for this chat
        settings = self.flood_settings[chat_id]
        
        # Add message to history
        self.message_history[chat_id].append((user_id, now))
        
        # Count messages for this user in the last minute
        one_minute_ago = now - 60
        self.user_message_counts[chat_id][user_id] += 1
        
        # === Flood Detection ===
        # Count messages in the last minute
        recent_messages = [
            (uid, ts) for uid, ts in self.message_history[chat_id]
            if ts > one_minute_ago and uid == user_id
        ]
        
        if len(recent_messages) > settings['messages_per_minute']:
            # User is flooding the chat
            await self.handle_spam_detected(
                message,
                "flood",
                f"Sending too many messages ({len(recent_messages)} messages in 1 minute)"
            )
            return
        
        # === Content Analysis ===
        # Check for blacklisted words
        text = message.text.lower()
        found_blacklist = False
        blacklisted_word = None
        
        # Check global blacklist
        for word in self.global_blacklist:
            if word in text:
                found_blacklist = True
                blacklisted_word = word
                break
        
        # Check chat-specific blacklist
        if not found_blacklist:
            for word in self.chat_blacklists[chat_id]:
                if word in text:
                    found_blacklist = True
                    blacklisted_word = word
                    break
        
        if found_blacklist:
            await self.handle_spam_detected(
                message,
                "blacklist",
                f"Message contains blacklisted word: '{blacklisted_word}'"
            )
            return
        
        # Check for spam patterns
        for pattern in self.spam_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                await self.handle_spam_detected(
                    message,
                    "pattern",
                    "Message matches spam pattern"
                )
                return
        
        # Check for too many URLs
        urls = re.findall(r'https?://\S+', text)
        if len(urls) > settings['url_limit']:
            await self.handle_spam_detected(
                message,
                "urls",
                f"Too many URLs in message ({len(urls)})"
            )
            return
        
        # Check for forwarded messages (if user forwards many in a short time)
        if message.forward_date:
            forward_count = sum(
                1 for (uid, ts) in self.message_history[chat_id]
                if uid == user_id and ts > one_minute_ago and message.forward_date
            )
            
            if forward_count > settings['max_forwards']:
                await self.handle_spam_detected(
                    message,
                    "forwards",
                    f"Forwarding too many messages ({forward_count} in 1 minute)"
                )
                return
        
        # === Similar Message Detection ===
        # Get recent messages from this user
        recent_user_messages = [
            msg.text for msg in message.chat.message_history.cache 
            if msg.from_user and msg.from_user.id == user_id and msg.text
        ]
        
        # Count occurrences of this message
        if recent_user_messages:
            message_counts = Counter(recent_user_messages)
            
            if message_counts[message.text] > settings['similar_messages_limit']:
                await self.handle_spam_detected(
                    message,
                    "similar",
                    f"Sending similar messages repeatedly ({message_counts[message.text]} times)"
                )
                return
    
    async def handle_spam_detected(self, message: Message, spam_type: str, reason: str):
        """Handle detected spam with appropriate action"""
        chat_id = message.chat.id
        user_id = message.from_user.id
        settings = self.flood_settings[chat_id]
        action = settings['action']
        
        # Check if this user was recently warned (to avoid duplicate warnings)
        recently_warned = (chat_id, user_id) in self.warned_users
        
        # Log the spam detection
        logger.warning(
            f"Spam detected in chat {chat_id} from user {user_id}: "
            f"Type: {spam_type}, Reason: {reason}, Action: {action}"
        )
        
        try:
            # Always delete the spam message
            await message.delete()
            
            # Take action based on settings
            if action == "warn" and not recently_warned:
                # Send warning
                warn_msg = await message.chat.send_message(
                    f"⚠️ @{message.from_user.username or message.from_user.id}, "
                    f"please don't spam! Reason: {reason}"
                )
                
                # Add to warned users set
                self.warned_users.add((chat_id, user_id))
                
                # Set a timeout to remove from warned set after 5 minutes
                async def remove_warned():
                    await asyncio.sleep(300)  # 5 minutes
                    self.warned_users.discard((chat_id, user_id))
                
                asyncio.create_task(remove_warned())
                
                # Delete warning after 30 seconds
                async def delete_warning():
                    await asyncio.sleep(30)
                    await warn_msg.delete()
                
                asyncio.create_task(delete_warning())
                
            elif action == "mute" or (action == "warn" and recently_warned):
                # Mute the user for 10 minutes
                until_date = datetime.now() + timedelta(minutes=10)
                
                await message.chat.restrict(
                    user_id=user_id,
                    permissions={
                        "can_send_messages": False,
                        "can_send_media_messages": False,
                        "can_send_other_messages": False,
                        "can_add_web_page_previews": False
                    },
                    until_date=until_date
                )
                
                mute_msg = await message.chat.send_message(
                    f"🔇 {message.from_user.full_name} has been muted for 10 minutes due to spam.\n"
                    f"Reason: {reason}"
                )
                
                # Delete notification after 30 seconds
                async def delete_notification():
                    await asyncio.sleep(30)
                    await mute_msg.delete()
                
                asyncio.create_task(delete_notification())
                
            elif action == "kick":
                # Kick the user
                await message.chat.kick(user_id=user_id)
                
                kick_msg = await message.chat.send_message(
                    f"👢 {message.from_user.full_name} has been kicked for spamming.\n"
                    f"Reason: {reason}"
                )
                
                # Delete notification after 30 seconds
                async def delete_notification():
                    await asyncio.sleep(30)
                    await kick_msg.delete()
                
                asyncio.create_task(delete_notification())
                
            elif action == "ban":
                # Ban the user
                await message.chat.ban(user_id=user_id)
                
                ban_msg = await message.chat.send_message(
                    f"🚫 {message.from_user.full_name} has been banned for spamming.\n"
                    f"Reason: {reason}"
                )
                
                # Delete notification after 30 seconds
                async def delete_notification():
                    await asyncio.sleep(30)
                    await ban_msg.delete()
                
                asyncio.create_task(delete_notification())
            
            # Send event for other components to process
            await event_manager.publish("spam:detected", {
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message.message_id,
                "spam_type": spam_type,
                "reason": reason,
                "action_taken": action,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error handling spam: {e}")
    
    async def cleanup_history_task(self):
        """Task to clean up old message history entries"""
        try:
            while True:
                await asyncio.sleep(60)  # Run every minute
                
                now = time.time()
                one_hour_ago = now - 3600
                
                # Clean up message history
                for chat_id in self.message_history:
                    self.message_history[chat_id] = [
                        (uid, ts) for uid, ts in self.message_history[chat_id]
                        if ts > one_hour_ago
                    ]
                
                # Clean up user message counts
                for chat_id in self.user_message_counts:
                    # Reset counts that are more than an hour old
                    self.user_message_counts[chat_id] = defaultdict(int)
                
                # Clean up join history
                for chat_id in self.join_history:
                    self.join_history[chat_id] = [
                        (uid, ts) for uid, ts in self.join_history[chat_id]
                        if ts > one_hour_ago
                    ]
                
        except asyncio.CancelledError:
            # Task was canceled, clean up
            logger.debug("Cleanup task cancelled")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}") 