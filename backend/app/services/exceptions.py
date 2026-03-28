from __future__ import annotations


class EntityNotFoundError(Exception):
    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id} not found")


class AuthError(Exception):
    """Base auth error."""


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid credentials")


class UsernameAlreadyExistsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Username already exists")


class InvalidTokenError(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid token")


class TokenExpiredError(AuthError):
    def __init__(self) -> None:
        super().__init__("Token expired")


class ReplayDetectedError(AuthError):
    def __init__(self) -> None:
        super().__init__("Token reuse detected, all sessions revoked")
