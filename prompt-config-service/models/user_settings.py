"""User settings models for managing user-specific configurations."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base


class UserProfile(Base):
    """Model for user profiles to track user creation."""
    
    __tablename__ = "user_profiles"
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user ID
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    placeholder_settings: Mapped[list["UserPlaceholderSetting"]] = relationship("UserPlaceholderSetting", back_populates="user")

    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id})>"


class UserPlaceholderSetting(Base):
    """Model for user-specific placeholder settings."""
    
    __tablename__ = "user_placeholder_settings"
    
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.user_id"), primary_key=True)
    placeholder_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("placeholders.id"), primary_key=True)
    placeholder_value_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("placeholder_values.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["UserProfile"] = relationship("UserProfile", back_populates="placeholder_settings")
    placeholder: Mapped["Placeholder"] = relationship("Placeholder", back_populates="user_settings")
    placeholder_value: Mapped["PlaceholderValue"] = relationship("PlaceholderValue", back_populates="user_settings")

    def __repr__(self) -> str:
        return f"<UserPlaceholderSetting(user_id={self.user_id}, placeholder_id='{self.placeholder_id}')>"