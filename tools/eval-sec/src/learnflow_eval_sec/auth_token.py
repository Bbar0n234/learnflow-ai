"""JWT exp parsing + token refresh orchestration (stdlib only).

We do NOT verify the signature — backend does that on each request. We only read
`exp` to decide when to proactively call /api/auth/refresh, so a base64 + json
decode is sufficient.
"""

from __future__ import annotations

import base64
import json
import time


def _b64decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def parse_exp(access_token: str) -> int:
    """Decode JWT payload and return `exp` as unix ts (seconds)."""

    parts = access_token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT (expected 3 segments)")
    payload = json.loads(_b64decode(parts[1]))
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("JWT payload missing integer exp")
    return exp


class TokenGuard:
    """Tracks access-token expiration and decides when to refresh."""

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._exp_ts: int = 0

    @property
    def access_token(self) -> str:
        if self._access_token is None:
            raise RuntimeError("TokenGuard.set() must be called before access_token")
        return self._access_token

    def set(self, access_token: str) -> None:
        self._access_token = access_token
        self._exp_ts = parse_exp(access_token)

    def should_refresh_now(self, slack_seconds: int = 60) -> bool:
        if self._access_token is None:
            return False
        return time.time() + slack_seconds >= self._exp_ts
