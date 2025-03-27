from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime
from typing import List, Optional

from app.models.base import BaseModel, Base


class UserRole(enum.Enum):
    """User role enumeration"""
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    GUEST = "guest"
    BANNED = "banned"


class User(BaseModel):
    """User model"""
    __tablename__ = "users"

    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String(10), default="en")
    role = Column(Enum(UserRole), default=UserRole.MEMBER)
    is_active = Column(Boolean, default=True)
    warnings_count = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, nullable=True)
    ban_date = Column(DateTime, nullable=True)
    
    # Relationships
    chats = relationship("ChatMember", back_populates="user")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username}, role={self.role})>"
        
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.username or str(self.telegram_id)
