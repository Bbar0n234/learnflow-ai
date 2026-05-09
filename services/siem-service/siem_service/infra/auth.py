"""JWT validation and RBAC for SIEM service."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from siem_service.config import get_settings

security = HTTPBearer()


class JWTValidator:
    """Validates HS256 JWT tokens with is_admin claim."""

    def __init__(self, jwt_secret: str) -> None:
        """Initialize validator with JWT secret."""
        self.jwt_secret = jwt_secret

    def validate_token(self, credentials: HTTPAuthorizationCredentials) -> dict:
        """Validate JWT token and return claims."""
        try:
            payload = jwt.decode(
                credentials.credentials,
                self.jwt_secret,
                algorithms=["HS256"],
            )
            return payload
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from e

    def get_user_id(self, payload: dict) -> str:
        """Extract user_id from JWT payload."""
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing 'sub' claim in token",
            )
        return str(user_id)

    def is_admin(self, payload: dict) -> bool:
        """Check if token has is_admin=true claim."""
        return payload.get("is_admin", False) is True


def get_jwt_validator() -> JWTValidator:
    """Get JWTValidator instance."""
    settings = get_settings()
    return JWTValidator(settings.jwt_secret)


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    validator: Annotated[JWTValidator, Depends(get_jwt_validator)],
) -> dict:
    """Dependency: validate JWT and check is_admin claim."""
    payload = validator.validate_token(credentials)

    if not validator.is_admin(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return payload


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    validator: Annotated[JWTValidator, Depends(get_jwt_validator)],
) -> dict:
    """Dependency: validate JWT and return claims."""
    return validator.validate_token(credentials)
