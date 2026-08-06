from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserMCPServer(Base):
    __tablename__ = "user_mcp_servers"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_tools: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectMCPServer(Base):
    __tablename__ = "project_mcp_servers"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_tools: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThreadMCPServer(Base):
    __tablename__ = "thread_mcp_servers"
    __table_args__ = (UniqueConstraint("thread_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("thread_views.thread_id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_tools: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MCPServerDisable(Base):
    __tablename__ = "mcp_server_disables"
    __table_args__ = (
        CheckConstraint("scope_type IN ('project', 'thread')", name="scope_type"),
    )

    scope_type: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    server_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
