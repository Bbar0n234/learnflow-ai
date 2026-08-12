"""PKCE primitives: solitary-unit on pure functions with no collaborators.

The S256 derivation is checked against the worked example of RFC 7636 § 4.2
rather than against a value recomputed the same way the implementation does —
an independent oracle, so a mistake shared by test and code cannot pass.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable

import pytest
from app.infra.oauth.pkce import (
    derive_code_challenge,
    generate_code_verifier,
    generate_state,
)

# RFC 7636 § 4.2 (Appendix B) worked example.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

_URL_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


@pytest.mark.unit
def test_derive_code_challenge_matches_rfc7636_example() -> None:
    assert derive_code_challenge(RFC_VERIFIER) == RFC_CHALLENGE


@pytest.mark.unit
def test_derive_code_challenge_is_unpadded_url_safe_base64() -> None:
    challenge = derive_code_challenge(generate_code_verifier())

    assert _URL_SAFE.match(challenge)  # no '+', '/' or '=' — URL-safe alphabet
    assert len(base64.urlsafe_b64decode(challenge + "==")) == 32  # SHA-256 digest


@pytest.mark.unit
def test_derive_code_challenge_differs_for_different_verifiers() -> None:
    assert derive_code_challenge("verifier-one") != derive_code_challenge("verifier-2")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("generate", "min_length"),
    [(generate_state, 32), (generate_code_verifier, 43)],
)
def test_generated_secrets_are_unique_and_long_enough(
    generate: Callable[[], str], min_length: int
) -> None:
    # Both are anti-guessing tokens: a repeat across calls would let one flow's
    # state or verifier stand in for another's.
    values = {generate() for _ in range(50)}

    assert len(values) == 50
    assert all(len(value) >= min_length for value in values)
