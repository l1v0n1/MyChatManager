from typing import Dict, List, Any, Optional, Union
from loguru import logger
from datetime import datetime
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.models.chat import Chat, ChatMember, ChatMemberStatus
from app.models.user import User


class ChatService:
    """Service for managing chats and chat members"""
    
    async def get_chat_by_telegram_id(self, telegram_id: int) -> Optional[Chat]:
        """Get a chat by its Telegram ID"""
        async with get_session() as session:
            query = select(Chat).where(Chat.telegram_id == telegram_id)
            result = await session.execute(query)
            return result.scalars().first()
    
    async def get_or_create_chat(
        self,
        telegram_id: int,
        title: str,
        chat_type: str,
    ) -> Chat:
        """Get or create a chat by its Telegram ID"""
        # First try to get the chat
        chat = await self.get_chat_by_telegram_id(telegram_id)
        
        # If chat doesn't exist, create it
        if not chat:
            async with get_session() as session:
                chat = Chat(
                    telegram_id=telegram_id,
                    title=title,
                    chat_type=chat_type,
                    is_active=True,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                session.add(chat)
                await session.commit()
                await session.refresh(chat)
                logger.info(f"Created new chat: {title} (ID: {telegram_id})")
        else:
            # Update chat if title has changed
            if chat.title != title:
                await self.update_chat(chat.id, {"title": title})
        
        return chat
    
    async def update_chat(self, chat_id: int, data: Dict[str, Any]) -> bool:
        """Update chat data"""
        async with get_session() as session:
            query = select(Chat).where(Chat.id == chat_id)
            result = await session.execute(query)
            chat = result.scalars().first()
            
            if not chat:
                return False
            
            # Update fields
            for key, value in data.items():
                if hasattr(chat, key):
                    setattr(chat, key, value)
            
            chat.updated_at = datetime.now()
            await session.commit()
            return True
    
    async def get_chat_member(self, chat_id: int, user_id: int) -> Optional[ChatMember]:
        """Get chat member"""
        async with get_session() as session:
            query = select(ChatMember).where(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id
            )
            result = await session.execute(query)
            return result.scalars().first()
    
    async def update_chat_member(
        self,
        chat_id: int,
        user_id: int,
        status: str
    ) -> ChatMember:
        """Update or create chat member"""
        # First try to get the chat member
        chat_member = await self.get_chat_member(chat_id, user_id)
        
        async with get_session() as session:
            if not chat_member:
                # Create new chat member record
                chat_member = ChatMember(
                    chat_id=chat_id,
                    user_id=user_id,
                    status=status,
                    joined_at=datetime.now(),
                    updated_at=datetime.now()
                )
                session.add(chat_member)
            else:
                # Update status if changed
                if chat_member.status != status:
                    chat_member.status = status
                    chat_member.updated_at = datetime.now()
            
            await session.commit()
            
            if chat_member.id:
                await session.refresh(chat_member)
            
            return chat_member
    
    async def list_chat_members(self, chat_id: int) -> List[ChatMember]:
        """List all members of a chat"""
        async with get_session() as session:
            query = select(ChatMember).where(ChatMember.chat_id == chat_id)
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def list_active_chats(self) -> List[Chat]:
        """List all active chats"""
        async with get_session() as session:
            query = select(Chat).where(Chat.is_active == True)
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_admin_chat_members(self, chat_id: int) -> List[ChatMember]:
        """Get all admin members of a chat"""
        async with get_session() as session:
            query = select(ChatMember).where(
                ChatMember.chat_id == chat_id,
                ChatMember.status.in_(["creator", "administrator"])
            )
            result = await session.execute(query)
            return list(result.scalars().all())


# Create a singleton instance
chat_service = ChatService() 