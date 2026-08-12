from __future__ import annotations


class OAuthProviderError(Exception):
    """A provider call failed: non-2xx response, timeout, or malformed payload.

    Internal exception of the oauth subsystem — narrow, carries no HTTP
    semantics, and is guaranteed to be caught before the HTTP barrier
    (conventions.md § Обработка ошибок, второй уровень нормы: прецедент
    ``AuthError`` in ``services/exceptions.py``). Routes catch it explicitly
    (T1.6) and map it onto the ``provider_unavailable`` ``/login?error=``
    branch — it must never reach ``app/api/problem.py``.
    """

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider}: {detail}")
