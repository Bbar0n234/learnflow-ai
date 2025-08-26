"""Placeholder models for managing prompt placeholders and their values."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from database import Base


class Placeholder(Base):
    """Model for prompt placeholders."""
    
    __tablename__ = "placeholders"
    
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    values: Mapped[list["PlaceholderValue"]] = relationship("PlaceholderValue", back_populates="placeholder")
    user_settings: Mapped[list["UserPlaceholderSetting"]] = relationship("UserPlaceholderSetting", back_populates="placeholder")
    profile_settings: Mapped[list["ProfilePlaceholderSetting"]] = relationship("ProfilePlaceholderSetting", back_populates="placeholder")

    def __repr__(self) -> str:
        return f"<Placeholder(name='{self.name}', display_name='{self.display_name}')>"


class PlaceholderValue(Base):
    """Model for placeholder values."""
    
    __tablename__ = "placeholder_values"
    
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    placeholder_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("placeholders.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Relationships
    placeholder: Mapped["Placeholder"] = relationship("Placeholder", back_populates="values")
    user_settings: Mapped[list["UserPlaceholderSetting"]] = relationship("UserPlaceholderSetting", back_populates="placeholder_value")
    profile_settings: Mapped[list["ProfilePlaceholderSetting"]] = relationship("ProfilePlaceholderSetting", back_populates="placeholder_value")

    def __repr__(self) -> str:
        return f"<PlaceholderValue(name='{self.name}', display_name='{self.display_name}', value='{self.value[:50]}...')>"