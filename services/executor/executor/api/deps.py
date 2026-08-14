"""Request-scoped dependencies for executor API routes."""

from typing import Annotated

from fastapi import Depends, Request

from executor.config import Settings


def get_settings(request: Request) -> Settings:
    """Get the app-state-owned Settings instance."""
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
