"""httpx wrapper: login/register/refresh + REST calls + SSE stream.

All state hermetic: HTTP only. No backend imports.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from learnflow_eval_sec.auth_token import TokenGuard
from learnflow_eval_sec.sse import SseEvent, aiter_sse


class RateLimitedAuthError(RuntimeError):
    """Hit /api/auth/login rate limit — do not retry."""


class EvalHttpClient:
    def __init__(
        self,
        base_url: str,
        token_guard: TokenGuard,
        timeout: float = 120.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, follow_redirects=False
        )
        self._token_guard = token_guard

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- Auth ----------------------------------------------------------

    async def ensure_user(self, name: str, password: str) -> str:
        """Idempotent user setup: login → 401 → register → 201 path.

        Returns access_token. Also primes token_guard and refresh cookie jar.
        Raises on 429 (rate-limit) or 409 (user exists, wrong password).
        """

        payload = {"name": name, "password": password}

        login_resp = await self._client.post("/api/auth/login", json=payload)
        if login_resp.status_code == 200:
            token = str(login_resp.json()["access_token"])
            self._token_guard.set(token)
            return token
        if login_resp.status_code == 429:
            retry_after = login_resp.headers.get("Retry-After", "?")
            raise RateLimitedAuthError(
                f"login rate-limited, retry after {retry_after}s — "
                "check EVAL_RUNNER_USERNAME/PASSWORD or wait"
            )
        if login_resp.status_code != 401:
            raise RuntimeError(
                f"login failed with unexpected status {login_resp.status_code}: "
                f"{login_resp.text}"
            )

        # 401 → user either not exists or wrong password.
        register_resp = await self._client.post("/api/auth/register", json=payload)
        if register_resp.status_code in (200, 201):
            token = str(register_resp.json()["access_token"])
            self._token_guard.set(token)
            return token
        if register_resp.status_code == 409:
            raise RuntimeError(
                "Username already exists but login failed with 401. "
                "Check EVAL_RUNNER_PASSWORD in .env.eval. "
                "Do NOT retry — rate-limit is 5/60s on login."
            )
        raise RuntimeError(
            f"register failed with status {register_resp.status_code}: "
            f"{register_resp.text}"
        )

    async def refresh_access_token(self) -> str:
        """Exchange refresh cookie (already in jar) for a fresh access token."""

        resp = await self._client.post("/api/auth/refresh")
        resp.raise_for_status()
        token = str(resp.json()["access_token"])
        self._token_guard.set(token)
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_guard.access_token}"}

    async def _ensure_fresh_token(self) -> None:
        if self._token_guard.should_refresh_now():
            await self.refresh_access_token()

    # ---- User-level state reset ---------------------------------------

    async def reset_user_state(self) -> dict[str, int]:
        """Wipe user-level state via public REST: memories, instructions, MCP servers.

        Returns counts of what was cleared — for stdout logging.
        """

        await self._ensure_fresh_token()
        counts: dict[str, int] = {"memories": 0, "mcp_servers": 0}

        # Memories
        memories_resp = await self._client.get(
            "/api/users/me/memories", headers=self._auth_headers()
        )
        memories_resp.raise_for_status()
        items = memories_resp.json().get("items", [])
        for item in items:
            key = item["key"]
            del_resp = await self._client.delete(
                f"/api/users/me/memories/{key}", headers=self._auth_headers()
            )
            del_resp.raise_for_status()
        counts["memories"] = len(items)

        # Custom instructions (PUT empty content)
        instr_resp = await self._client.put(
            "/api/users/me/instructions",
            headers=self._auth_headers(),
            json={"content": ""},
        )
        instr_resp.raise_for_status()

        # User-level MCP servers
        mcp_resp = await self._client.get(
            "/api/users/me/mcp-servers", headers=self._auth_headers()
        )
        mcp_resp.raise_for_status()
        servers = mcp_resp.json().get("items", [])
        for s in servers:
            sid = s["id"]
            del_resp = await self._client.delete(
                f"/api/users/me/mcp-servers/{sid}", headers=self._auth_headers()
            )
            del_resp.raise_for_status()
        counts["mcp_servers"] = len(servers)

        return counts

    async def verify_clean_state(self) -> dict[str, int | str]:
        """Sanity check after reset_user_state (for TC-6.3.3)."""

        await self._ensure_fresh_token()
        memories = (
            (
                await self._client.get(
                    "/api/users/me/memories", headers=self._auth_headers()
                )
            )
            .json()
            .get("items", [])
        )
        instructions = (
            (
                await self._client.get(
                    "/api/users/me/instructions", headers=self._auth_headers()
                )
            )
            .json()
            .get("content", "")
        )
        mcp = (
            (
                await self._client.get(
                    "/api/users/me/mcp-servers", headers=self._auth_headers()
                )
            )
            .json()
            .get("items", [])
        )
        return {
            "memories": len(memories),
            "instructions_len": len(instructions),
            "mcp_servers": len(mcp),
        }

    # ---- Project / chat ------------------------------------------------

    async def create_project(self, name: str) -> uuid.UUID:
        await self._ensure_fresh_token()
        resp = await self._client.post(
            "/api/projects", headers=self._auth_headers(), json={"name": name}
        )
        resp.raise_for_status()
        return uuid.UUID(resp.json()["id"])

    async def create_chat(
        self, project_id: uuid.UUID, title: str | None = None
    ) -> uuid.UUID:
        await self._ensure_fresh_token()
        resp = await self._client.post(
            f"/api/projects/{project_id}/chats",
            headers=self._auth_headers(),
            json={"title": title} if title else {},
        )
        resp.raise_for_status()
        return uuid.UUID(resp.json()["thread_id"])

    async def get_chat_messages_count(
        self, project_id: uuid.UUID, chat_id: uuid.UUID
    ) -> int:
        await self._ensure_fresh_token()
        resp = await self._client.get(
            f"/api/projects/{project_id}/chats/{chat_id}",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return len(resp.json().get("messages", []))

    # ---- SSE streaming ------------------------------------------------

    @asynccontextmanager
    async def stream_message(
        self, project_id: uuid.UUID, chat_id: uuid.UUID, content: str
    ) -> AsyncIterator[AsyncIterator[SseEvent]]:
        """Post a message and yield an async iterator over SSE events."""

        await self._ensure_fresh_token()
        url = f"/api/projects/{project_id}/chats/{chat_id}/messages"
        async with self._client.stream(
            "POST",
            url,
            headers={**self._auth_headers(), "Accept": "text/event-stream"},
            json={"content": content},
        ) as response:
            response.raise_for_status()
            yield aiter_sse(response)
