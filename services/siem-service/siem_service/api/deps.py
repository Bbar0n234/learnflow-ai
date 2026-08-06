"""Request-scoped dependencies for SIEM API routes."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.infra.auth import require_admin
from siem_service.infra.db import get_session
from siem_service.pipeline.meta_emitter import MetaEmitter


def get_meta_emitter(request: Request) -> MetaEmitter:
    """Get the lifespan-owned MetaEmitter from app state."""
    return request.app.state.meta_emitter


SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminPayload = Annotated[dict, Depends(require_admin)]
MetaEmitterDep = Annotated[MetaEmitter, Depends(get_meta_emitter)]
