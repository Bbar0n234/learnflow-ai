from __future__ import annotations

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.services.exceptions import EncryptionError

logger = structlog.get_logger()


class EncryptionService:
    """Fernet encryption wrapper with disabled mode when key is not configured."""

    def __init__(self, key: str) -> None:
        self._fernet: Fernet | None = None
        if key:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            logger.warning(
                "encryption key not configured, MCP API key storage disabled"
            )

    @property
    def is_available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> bytes:
        if self._fernet is None:
            raise RuntimeError(
                "Encryption not available: MCP_ENCRYPTION_KEY not configured"
            )
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        if self._fernet is None:
            raise RuntimeError(
                "Decryption not available: MCP_ENCRYPTION_KEY not configured"
            )
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as e:
            logger.error("decryption failed: invalid or corrupted token", exc_info=True)
            raise EncryptionError(
                "Decryption failed: invalid or corrupted ciphertext"
            ) from e
