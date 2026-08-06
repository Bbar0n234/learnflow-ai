"""EncryptionService: Fernet round-trip, tamper detection, disabled mode.

Solitary-unit — the service wraps a pure crypto primitive with no I/O.
"""

from __future__ import annotations

import pytest
from app.services.encryption import EncryptionService
from app.services.exceptions import EncryptionError
from cryptography.fernet import Fernet


def _service() -> EncryptionService:
    return EncryptionService(Fernet.generate_key().decode())


@pytest.mark.unit
@pytest.mark.parametrize(
    "plaintext",
    ["sk-secret-api-key", "", "ключ-с-юникодом-🔐", "x" * 4096],
)
def test_encrypt_then_decrypt_round_trips(plaintext: str) -> None:
    service = _service()

    ciphertext = service.encrypt(plaintext)

    assert isinstance(ciphertext, bytes)
    assert ciphertext != plaintext.encode()
    assert service.decrypt(ciphertext) == plaintext


@pytest.mark.unit
def test_available_when_key_configured() -> None:
    assert _service().is_available is True


@pytest.mark.unit
def test_decrypt_corrupted_ciphertext_raises_encryption_error() -> None:
    service = _service()

    with pytest.raises(EncryptionError):
        service.decrypt(b"not-a-valid-fernet-token")


@pytest.mark.unit
def test_decrypt_with_wrong_key_raises_encryption_error() -> None:
    producer = _service()
    consumer = _service()  # different key
    ciphertext = producer.encrypt("payload")

    with pytest.raises(EncryptionError):
        consumer.decrypt(ciphertext)


@pytest.mark.unit
def test_disabled_without_key_reports_unavailable() -> None:
    assert EncryptionService("").is_available is False


@pytest.mark.unit
def test_encrypt_disabled_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        EncryptionService("").encrypt("payload")


@pytest.mark.unit
def test_decrypt_disabled_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        EncryptionService("").decrypt(b"whatever")
