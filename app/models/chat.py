from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime
from typing import List, Optional

from app.models.base import BaseModel, Base
from app.models.user import UserRole


class ChatType(enum.Enum):
    """Chat type enumeration"""
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class ChatMemberStatus(enum.Enum):
    """Chat member status enumeration"""
    CREATOR = "creator"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"
    LEFT = "left"
    KICKED = "kicked"


class Chat(BaseModel):
    """Chat model"""
    __tablename__ = "chats"

    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    chat_type = Column(Enum(ChatType), nullable=False)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    invite_link = Column(String, nullable=True)
    
    # Settings
    welcome_message = Column(Text, nullable=True)
    rules = Column(Text, nullable=True)
    language = Column(String(10), default="en")
    auto_delete_service_messages = Column(Boolean, default=True)
    auto_delete_join_messages = Column(Boolean, default=True)
    require_approval = Column(Boolean, default=False)
    anti_spam_enabled = Column(Boolean, default=True)
    anti_flood_enabled = Column(Boolean, default=True)
    max_warnings = Column(Integer, default=3)
    flood_threshold = Column(Integer, default=5)  # messages per second
    
    # Relationships
    members = relationship("ChatMember", back_populates="chat", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, telegram_id={self.telegram_id}, title={self.title}, type={self.chat_type})>"


class ChatMember(BaseModel):
    """Chat member model"""
    __tablename__ = "chat_members"

    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(ChatMemberStatus), default=ChatMemberStatus.MEMBER)
    role = Column(Enum(UserRole), default=UserRole.MEMBER)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    muted_until = Column(DateTime, nullable=True)
    warnings_count = Column(Integer, default=0)
    
    # Relationships
    chat = relationship("Chat", back_populates="members")
    user = relationship("User", back_populates="chats")
    
    def __repr__(self) -> str:
        return f"<ChatMember(chat_id={self.chat_id}, user_id={self.user_id}, status={self.status}, role={self.role})>"
