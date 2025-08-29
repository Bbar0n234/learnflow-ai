"""API models for authentication."""

from pydantic import BaseModel, Field


class AuthCodeRequest(BaseModel):
    """Request model for auth code verification."""
    username: str = Field(..., description="Username")
    code: str = Field(..., description="6-character auth code")


class AuthTokenResponse(BaseModel):
    """Response model for successful authentication."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")