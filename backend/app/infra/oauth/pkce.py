from __future__ import annotations

import base64
import hashlib
import secrets


def generate_state() -> str:
    """CSRF-protection token for the OAuth flow (opaque, ≥256 bits)."""
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    """PKCE ``code_verifier`` (RFC 7636 § 4.1)."""
    return secrets.token_urlsafe(64)


def derive_code_challenge(verifier: str) -> str:
    """PKCE S256 ``code_challenge`` derived from a ``code_verifier`` (RFC 7636 § 4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
