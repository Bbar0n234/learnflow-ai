from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.artifact_blob import ArtifactBlob
    from app.models.project import Project
    from app.models.thread_view import ThreadView


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("thread_views.thread_id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project: Mapped[Project] = relationship(back_populates="artifacts")
    thread_view: Mapped[ThreadView | None] = relationship(back_populates="artifacts")
    blob: Mapped[ArtifactBlob | None] = relationship(
        back_populates="artifact", passive_deletes=True
    )
