from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.base import get_db_session
from app.models.user import User, UserRole
from app.models.chat import Chat, ChatMember, ChatMemberStatus
from app.services.cache_service import cache_service
from app.events.event_manager import event_manager


class UserService:
    """Service for managing users"""
    
    @staticmethod
    async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
        """Get a user by Telegram ID"""
        # Try to get from cache first
        cache_key = f"user:telegram:{telegram_id}"
        cached_user = await cache_service.get_model(cache_key, User)
        if cached_user:
            return cached_user
        
        # If not in cache, get from database
        async with get_db_session() as session:
            query = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(query)
            user = result.scalars().first()
            
            # If found, cache for future use
            if user:
                await cache_service.set_model(cache_key, user)
            
            return user
    
    @staticmethod
    async def create_or_update_user(
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> User:
        """Create or update a user"""
        # Try to get existing user
        user = await UserService.get_user_by_telegram_id(telegram_id)
        
        async with get_db_session() as session:
            if user:
                # Update existing user
                user.username = username or user.username
                user.first_name = first_name or user.first_name
                user.last_name = last_name or user.last_name
                user.language_code = language_code or user.language_code
                
                session.add(user)
                await session.commit()
                
                # Update cache
                cache_key = f"user:telegram:{telegram_id}"
                await cache_service.set_model(cache_key, user)
                
                logger.debug(f"Updated user: {user}")
            else:
                # Create new user
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language_code=language_code,
                )
                
                session.add(user)
                await session.commit()
                
                # Cache the new user
                cache_key = f"user:telegram:{telegram_id}"
                await cache_service.set_model(cache_key, user)
                
                logger.info(f"Created new user: {user}")
                
                # Publish user created event
                await event_manager.publish("user:created", {
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "username": user.username
                })
            
            return user
    
    @staticmethod
    async def set_user_role(user_id: int, role: UserRole) -> bool:
        """Set a user's role"""
        async with get_db_session() as session:
            query = select(User).where(User.id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            
            if not user:
                logger.warning(f"Cannot set role: User {user_id} not found")
                return False
            
            prev_role = user.role
            user.role = role
            session.add(user)
            await session.commit()
            
            # Update cache
            cache_key = f"user:telegram:{user.telegram_id}"
            await cache_service.set_model(cache_key, user)
            
            # Publish role changed event
            await event_manager.publish("user:role_changed", {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "previous_role": prev_role.value,
                "new_role": role.value
            })
            
            logger.info(f"Updated user {user.id} role from {prev_role} to {role}")
            return True
    
    @staticmethod
    async def ban_user(
        user_id: int,
        reason: Optional[str] = None,
        duration: Optional[int] = None,  # in seconds, None for permanent
        chat_id: Optional[int] = None  # If set, ban only in this chat
    ) -> bool:
        """Ban a user globally or in a specific chat"""
        async with get_db_session() as session:
            query = select(User).where(User.id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            
            if not user:
                logger.warning(f"Cannot ban: User {user_id} not found")
                return False
            
            ban_date = datetime.now()
            ban_until = None
            
            if chat_id:
                # Ban in specific chat
                chat_query = select(Chat).where(Chat.id == chat_id)
                chat_result = await session.execute(chat_query)
                chat = chat_result.scalars().first()
                
                if not chat:
                    logger.warning(f"Cannot ban: Chat {chat_id} not found")
                    return False
                
                # Get the chat member record
                member_query = select(ChatMember).where(
                    (ChatMember.user_id == user_id) & 
                    (ChatMember.chat_id == chat_id)
                )
                member_result = await session.execute(member_query)
                member = member_result.scalars().first()
                
                if not member:
                    logger.warning(f"Cannot ban: User {user_id} is not a member of chat {chat_id}")
                    return False
                
                # Update member status
                member.status = ChatMemberStatus.KICKED
                member.is_active = False
                
                session.add(member)
                await session.commit()
                
                # Publish ban event
                await event_manager.publish("user:banned", {
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "chat_id": chat_id,
                    "reason": reason,
                    "duration": duration,
                    "ban_date": ban_date.isoformat()
                })
                
                logger.info(f"Banned user {user.id} from chat {chat_id}: {reason}")
            else:
                # Global ban
                user.is_banned = True
                user.role = UserRole.BANNED
                user.ban_reason = reason
                user.ban_date = ban_date
                
                session.add(user)
                await session.commit()
                
                # Update cache
                cache_key = f"user:telegram:{user.telegram_id}"
                await cache_service.set_model(cache_key, user)
                
                # Publish ban event
                await event_manager.publish("user:banned", {
                    "user_id": user.id,
                    "telegram_id": user.telegram_id,
                    "global": True,
                    "reason": reason,
                    "duration": duration,
                    "ban_date": ban_date.isoformat()
                })
                
                logger.info(f"Globally banned user {user.id}: {reason}")
            
            return True
    
    @staticmethod
    async def warn_user(
        user_id: int,
        chat_id: int,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Warn a user in a chat"""
        async with get_db_session() as session:
            # Get user and chat
            user_query = select(User).where(User.id == user_id)
            user_result = await session.execute(user_query)
            user = user_result.scalars().first()
            
            chat_query = select(Chat).where(Chat.id == chat_id)
            chat_result = await session.execute(chat_query)
            chat = chat_result.scalars().first()
            
            if not user or not chat:
                logger.warning(f"Cannot warn: User {user_id} or Chat {chat_id} not found")
                return {"success": False, "message": "User or chat not found"}
            
            # Get chat member
            member_query = select(ChatMember).where(
                (ChatMember.user_id == user_id) & 
                (ChatMember.chat_id == chat_id)
            )
            member_result = await session.execute(member_query)
            member = member_result.scalars().first()
            
            if not member:
                logger.warning(f"Cannot warn: User {user_id} is not a member of chat {chat_id}")
                return {"success": False, "message": "User is not a member of the chat"}
            
            # Increment warnings
            member.warnings_count += 1
            session.add(member)
            await session.commit()
            
            # Publish warning event
            await event_manager.publish("user:warned", {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "chat_id": chat_id,
                "reason": reason,
                "warning_count": member.warnings_count
            })
            
            logger.info(f"Warned user {user.id} in chat {chat_id}: {reason} (Count: {member.warnings_count})")
            
            # Check if warning threshold is reached
            if chat.max_warnings and member.warnings_count >= chat.max_warnings:
                # Ban user from chat
                await UserService.ban_user(
                    user_id=user_id,
                    chat_id=chat_id,
                    reason=f"Exceeded maximum warnings ({chat.max_warnings})"
                )
                return {
                    "success": True,
                    "warnings": member.warnings_count,
                    "banned": True,
                    "message": f"User banned after {member.warnings_count} warnings"
                }
            
            return {
                "success": True,
                "warnings": member.warnings_count,
                "banned": False,
                "message": f"User warned ({member.warnings_count}/{chat.max_warnings})"
            }


# Create singleton instance
user_service = UserService()
