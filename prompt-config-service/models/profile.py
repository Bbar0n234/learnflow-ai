"""Profile models for managing prompt configuration profiles."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base


class Profile(Base):
    """Model for prompt configuration profiles."""
    
    __tablename__ = "profiles"
    
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "style", "subject"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    placeholder_settings: Mapped[list["ProfilePlaceholderSetting"]] = relationship("ProfilePlaceholderSetting", back_populates="profile")

    def __repr__(self) -> str:
        return f"<Profile(name='{self.name}', display_name='{self.display_name}', category='{self.category}')>"


class ProfilePlaceholderSetting(Base):
    """Model for profile-specific placeholder settings."""
    
    __tablename__ = "profile_placeholder_settings"
    
    profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id"), primary_key=True)
    placeholder_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("placeholders.id"), primary_key=True)
    placeholder_value_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("placeholder_values.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    profile: Mapped["Profile"] = relationship("Profile", back_populates="placeholder_settings")
    placeholder: Mapped["Placeholder"] = relationship("Placeholder", back_populates="profile_settings")
    placeholder_value: Mapped["PlaceholderValue"] = relationship("PlaceholderValue", back_populates="profile_settings")

    def __repr__(self) -> str:
        try:
            return f"<ProfilePlaceholderSetting(profile_id='{self.profile_id}', placeholder_id='{self.placeholder_id}')>"
        except:
            return "<ProfilePlaceholderSetting(detached)>"