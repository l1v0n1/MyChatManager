"""
Notes Plugin for MyChatManager
Save and retrieve notes for group chats with markdown support
"""
from typing import Dict, Callable, Any, List, Optional
import re
import asyncio
from datetime import datetime
from aiogram import Router, F, html
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.formatting import Text, Bold, Italic, Code, Pre, Underline
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from app.plugins.plugin_manager import PluginBase, PluginMetadata
from app.services.user_service import user_service
from app.models.user import User, UserRole
from app.utils.decorators import admin_required, moderator_required, log_command, chat_type


class NotesPlugin(PluginBase):
    """Plugin for saving and retrieving group notes"""
    
    # Define plugin metadata
    metadata = PluginMetadata(
        name="notes",
        version="1.0.0",
        description="Save and retrieve notes for group chats with markdown support",
        author="MyChatManager Team",
        requires=[],
        conflicts=[]
    )
    
    def __init__(self, manager):
        """Initialize the plugin"""
        super().__init__(manager)
        self.router = Router(name="notes")
        
        # In-memory storage for notes - in a full implementation, this would use database storage
        # Structure: {chat_id: {note_name: {"text": note_text, "creator_id": user_id, "created_at": timestamp}}}
        self.notes = {}
        
        # Register handlers
        self.router.message(Command("save"))(self.cmd_save_note)
        self.router.message(Command("get"))(self.cmd_get_note)
        self.router.message(Command("notes"))(self.cmd_list_notes)
        self.router.message(Command("clear"))(self.cmd_clear_note)
        self.router.message(Command("clearall"))(self.cmd_clear_all_notes)
        self.router.message(F.text.regexp(r"#([a-zA-Z0-9_]+)"))(self.handle_hashtag)
        
        # Register callback query handlers
        self.router.callback_query(F.data.startswith("note_"))(self.handle_note_callback)
    
    async def activate(self) -> bool:
        """Activate the plugin"""
        logger.info(f"Activating {self.metadata.name} plugin...")
        return await super().activate()
    
    def get_handlers(self) -> Dict[str, Callable]:
        """Get plugin command handlers"""
        return {
            "save": self.cmd_save_note,
            "get": self.cmd_get_note,
            "notes": self.cmd_list_notes,
            "clear": self.cmd_clear_note,
            "clearall": self.cmd_clear_all_notes
        }
    
    def get_middlewares(self) -> List[Any]:
        """Get plugin middlewares"""
        return []
    
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_save_note(self, message: Message, command: CommandObject, **kwargs):
        """Save a note for the chat"""
        if not command.args:
            await message.reply(
                "❌ Please provide a name for your note.\n"
                "Usage: /save <name> <content> or reply to a message with /save <name>"
            )
            return
        
        args = command.args.split(maxsplit=1)
        note_name = args[0].lower()
        
        # Validate note name
        if not re.match(r'^[a-zA-Z0-9_]+$', note_name):
            await message.reply(
                "❌ Note names can only contain letters, numbers, and underscores."
            )
            return
        
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Initialize chat notes if not exists
        if chat_id not in self.notes:
            self.notes[chat_id] = {}
        
        # Get note content from either message text or replied message
        if len(args) > 1:
            # Note content is in the command text
            note_text = args[1]
        elif message.reply_to_message:
            # Note content is in the replied message
            if message.reply_to_message.text:
                note_text = message.reply_to_message.text
            elif message.reply_to_message.caption:
                note_text = message.reply_to_message.caption
            else:
                await message.reply(
                    "❌ I can only save text messages as notes."
                )
                return
        else:
            await message.reply(
                "❌ Please provide content for your note or reply to a message."
            )
            return
        
        # Save the note
        self.notes[chat_id][note_name] = {
            "text": note_text,
            "creator_id": user_id,
            "created_at": datetime.now().isoformat(),
            "media_id": None  # For future implementation with media support
        }
        
        await message.reply(
            f"✅ Note <b>{html.quote(note_name)}</b> saved successfully!\n"
            f"You can retrieve it with <code>/get {note_name}</code> or <code>#{note_name}</code>."
        )
    
    @log_command
    @chat_type("group", "supergroup", "private")
    async def cmd_get_note(self, message: Message, command: CommandObject, **kwargs):
        """Retrieve a note"""
        if not command.args:
            await message.reply(
                "❌ Please specify which note to retrieve.\n"
                "Usage: /get <name>"
            )
            return
        
        note_name = command.args.lower()
        chat_id = message.chat.id
        
        # For private chats, check if a specific chat was mentioned
        if message.chat.type == "private" and ":" in note_name:
            parts = note_name.split(":", 1)
            try:
                chat_id = int(parts[0])
                note_name = parts[1]
            except ValueError:
                await message.reply(
                    "❌ Invalid chat ID format. Use /get chat_id:note_name"
                )
                return
        
        # Check if the note exists
        if chat_id not in self.notes or note_name not in self.notes[chat_id]:
            if message.chat.type == "private":
                await message.reply(
                    f"❌ Note <b>{html.quote(note_name)}</b> not found in chat {chat_id}."
                )
            else:
                await message.reply(
                    f"❌ Note <b>{html.quote(note_name)}</b> not found in this chat."
                )
            return
        
        # Retrieve and send the note
        note = self.notes[chat_id][note_name]
        
        # Get note creator info if possible
        creator_info = ""
        try:
            creator = await user_service.get_user(note["creator_id"])
            if creator:
                creator_info = f"Created by: {creator.first_name}"
        except Exception:
            pass
        
        # Send the note with formatting
        await message.reply(
            note["text"],
            disable_web_page_preview=False  # Allow links to show previews
        )
    
    @log_command
    @chat_type("group", "supergroup", "private")
    async def cmd_list_notes(self, message: Message, **kwargs):
        """List all notes in the chat"""
        chat_id = message.chat.id
        
        # Check if there are any notes for this chat
        if chat_id not in self.notes or not self.notes[chat_id]:
            await message.reply(
                "📝 No notes have been saved in this chat yet.\n"
                "To save a note, use /save <name> <content>"
            )
            return
        
        # Build list of notes
        notes_list = sorted(self.notes[chat_id].keys())
        
        # Build keyboard with note buttons
        builder = InlineKeyboardBuilder()
        for note_name in notes_list:
            builder.button(
                text=note_name,
                callback_data=f"note_{note_name}"
            )
        
        # Organize in grid (3 buttons per row)
        builder.adjust(3)
        
        await message.reply(
            f"📝 <b>Available Notes in this chat:</b>\n"
            f"Total: {len(notes_list)}\n\n"
            f"Click a button below to view a note, or use /get <name> or #name to retrieve a specific note.",
            reply_markup=builder.as_markup()
        )
    
    @moderator_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_clear_note(self, message: Message, command: CommandObject, **kwargs):
        """Delete a note from the chat"""
        if not command.args:
            await message.reply(
                "❌ Please specify which note to delete.\n"
                "Usage: /clear <name>"
            )
            return
        
        note_name = command.args.lower()
        chat_id = message.chat.id
        
        # Check if the note exists
        if chat_id not in self.notes or note_name not in self.notes[chat_id]:
            await message.reply(
                f"❌ Note <b>{html.quote(note_name)}</b> not found in this chat."
            )
            return
        
        # Delete the note
        del self.notes[chat_id][note_name]
        
        # If this was the last note, remove the chat entry
        if not self.notes[chat_id]:
            del self.notes[chat_id]
        
        await message.reply(
            f"✅ Note <b>{html.quote(note_name)}</b> has been deleted."
        )
    
    @admin_required
    @log_command
    @chat_type("group", "supergroup")
    async def cmd_clear_all_notes(self, message: Message, **kwargs):
        """Delete all notes from the chat"""
        chat_id = message.chat.id
        
        # Check if there are any notes for this chat
        if chat_id not in self.notes or not self.notes[chat_id]:
            await message.reply(
                "📝 There are no notes to clear in this chat."
            )
            return
        
        # Count notes
        note_count = len(self.notes[chat_id])
        
        # Create confirmation buttons
        confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, delete all notes",
                    callback_data=f"note_clearall_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ No, keep the notes",
                    callback_data=f"note_clearall_cancel"
                )
            ]
        ])
        
        await message.reply(
            f"⚠️ Are you sure you want to delete ALL {note_count} notes in this chat?\n"
            f"This action cannot be undone!",
            reply_markup=confirm_keyboard
        )
    
    async def handle_hashtag(self, message: Message, **kwargs):
        """Handle hashtag note retrieval (#notename)"""
        # Extract all hashtags from the message
        matches = re.findall(r"#([a-zA-Z0-9_]+)", message.text)
        
        if not matches:
            return
        
        chat_id = message.chat.id
        
        # We'll only process the first hashtag to avoid spam
        note_name = matches[0].lower()
        
        # Check if this is actually a note
        if chat_id in self.notes and note_name in self.notes[chat_id]:
            # Retrieve and send the note
            note = self.notes[chat_id][note_name]
            await message.reply(note["text"], disable_web_page_preview=False)
    
    async def handle_note_callback(self, callback_query: CallbackQuery, **kwargs):
        """Handle callback queries for notes"""
        await callback_query.answer()
        
        chat_id = callback_query.message.chat.id
        data = callback_query.data
        
        if data == "note_clearall_confirm":
            # Confirm clearing all notes
            if chat_id in self.notes:
                del self.notes[chat_id]
                await callback_query.message.edit_text(
                    "✅ All notes have been deleted from this chat."
                )
            else:
                await callback_query.message.edit_text(
                    "❌ There are no notes to clear in this chat."
                )
            
        elif data == "note_clearall_cancel":
            # Cancel clearing all notes
            await callback_query.message.edit_text(
                "✅ Operation cancelled. Your notes are safe."
            )
            
        else:
            # Display a specific note
            note_name = data[5:]  # Remove 'note_' prefix
            
            if chat_id in self.notes and note_name in self.notes[chat_id]:
                note = self.notes[chat_id][note_name]
                
                # Send as a new message rather than editing the list
                await callback_query.message.reply(
                    note["text"],
                    disable_web_page_preview=False
                ) 