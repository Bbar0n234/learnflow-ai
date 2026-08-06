from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base domain exception.

    Carries a machine-readable ``code`` (kebab-case), a default HTTP ``status``,
    and a client-safe ``detail`` message.  No transport knowledge — no fastapi /
    HTTP imports here.
    """

    code: str = "error"
    status: int = 500

    def __init__(
        self,
        detail: str | None = None,
        *,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        self.detail: str = detail or "An unexpected error occurred"
        self.extensions: dict[str, Any] = extensions or {}
        super().__init__(self.detail)


class NotFoundError(AppError):
    code = "entity-not-found"
    status = 404

    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(detail)


class ConflictError(AppError):
    code = "conflict"
    status = 409

    def __init__(self, detail: str = "Conflict") -> None:
        super().__init__(detail)


class SecurityPolicyViolationError(AppError):
    """Security guard rejected the input (injection / SSRF)."""

    code = "security-policy-violation"
    status = 422

    def __init__(
        self,
        *,
        reason: str,
        detail: str = "Security policy violation",
    ) -> None:
        super().__init__(detail, extensions={"reason": reason})
        self.reason = reason


class UpstreamUnavailableError(AppError):
    """An external dependency (MCP, wkhtmltopdf, …) is unreachable or misconfigured."""

    # code and status are configurable per-instance
    code = "upstream-unavailable"
    status = 503

    def __init__(
        self,
        *,
        code: str = "upstream-unavailable",
        status: int = 503,
        detail: str = "Upstream service unavailable",
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.status = status


class EncryptionError(AppError):
    """Encryption / decryption operation failed (e.g. corrupted ciphertext)."""

    code = "encryption-error"
    status = 500

    def __init__(self, detail: str = "Encryption operation failed") -> None:
        super().__init__(detail)


class InvalidURLError(AppError):
    """URL is syntactically invalid or hostname cannot be resolved (DNS failure)."""

    code = "invalid-url"
    status = 400

    def __init__(self, detail: str = "Invalid URL") -> None:
        super().__init__(detail)


class EntityNotFoundError(NotFoundError):
    """Backwards-compatible not-found error.

    Preserves original ``__init__(entity, entity_id)`` contract — imported
    from 6 places (project.py, artifact.py, chat.py, services/__init__.py,
    main.py).  ``detail`` is safe for the client; ``args[0]`` / ``str(exc)``
    carry entity + id for logs.
    """

    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__("Resource not found")
        # Override args so logs see entity + id (str(exc) / exc.args)
        self.args = (f"{entity} {entity_id} not found",)


# ---------------------------------------------------------------------------
# Auth errors — stay LOCAL (handled in routes/auth.py — etalon F-API-08).
# Consolidation into AppError is OQ-4, deferred.
# ---------------------------------------------------------------------------


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
