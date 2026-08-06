"""Точечные автотесты критичного пути auth: хэширование и токены.

Slice feat-004: argon2 уведён в threadpool (anyio.to_thread) — сами функции
остались синхронными, контракт фиксируем здесь.
"""

from app.services.security import (
    generate_refresh_token,
    hash_password,
    hash_raw_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    digest = hash_password("secret123")
    assert digest != "secret123"
    assert verify_password(digest, "secret123")


def test_password_verify_rejects_wrong_password() -> None:
    digest = hash_password("secret123")
    assert not verify_password(digest, "wrong")


def test_hash_raw_token_deterministic() -> None:
    assert hash_raw_token("abc") == hash_raw_token("abc")
    assert hash_raw_token("abc") != hash_raw_token("abd")


def test_generate_refresh_token_pair_consistent() -> None:
    raw, token_hash = generate_refresh_token()
    assert hash_raw_token(raw) == token_hash
