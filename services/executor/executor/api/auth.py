"""Shared-secret authentication of the executor's job surface.

The `exec` network segment isolates the executor, but isolation alone makes
the segment a single point of failure: `POST /jobs` runs arbitrary code and
takes `project_id` as an ordinary request field, so anything that reaches the
port gets rw access to *every* project's workspace. This module is the second
barrier — the caller must present the `EXECUTOR_AUTH_TOKEN` shared with the
backend (`app.infra.executor`).

`Authorization: Bearer <token>` rather than a bespoke header: every other
machine-to-machine call in this repo already speaks Bearer (the backend's own
`app/api/deps.py`, siem-service's `HTTPBearer`, the MCP client's outbound
`Authorization` header), and no custom auth header exists anywhere in the
project to be consistent with instead.

`GET /health` deliberately stays open — compose's healthcheck polls it and it
reveals nothing but liveness plus the sandbox degradation flag.
"""

import hmac
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from executor.api.deps import SettingsDep

logger = structlog.get_logger()

# `auto_error=False`: the built-in error is a 403 "Not authenticated" with no
# `WWW-Authenticate` header and no log line — this module answers both the
# missing and the mismatching case itself, identically, so a caller learns
# nothing from the difference.
_bearer = HTTPBearer(auto_error=False)

CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing executor auth token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_service_token(
    settings: SettingsDep,
    credentials: CredentialsDep,
) -> None:
    """Reject the request unless it carries the backend's shared secret.

    Raises:
        HTTPException: 401 when the `Authorization: Bearer` header is absent,
            malformed or carries the wrong token.
    """
    if credentials is None:
        logger.warning("executor auth rejected", reason="missing_credentials")
        raise _unauthorized()

    # `compare_digest` — the comparison is against a secret, so it must not
    # leak its prefix length through timing.
    if not hmac.compare_digest(credentials.credentials, settings.auth_token):
        logger.warning("executor auth rejected", reason="token_mismatch")
        raise _unauthorized()
