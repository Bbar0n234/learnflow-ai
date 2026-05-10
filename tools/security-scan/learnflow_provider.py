"""Promptfoo Python provider for LearnFlowAI red team scan.

Promptfoo loads this file via ``file://./learnflow_provider.py`` and calls
``call_api(prompt, options, context)`` for each test case. Each call:

1. Ensures eval-user is logged in (lazy login/register on first call).
2. Ensures a per-run project exists.
3. Creates a NEW chat for this test case (so a blocked thread does not
   poison subsequent cases — see design-brief §4.1, §6.3).
4. Streams the message through the existing SSE endpoint.
5. Normalises the result into Promptfoo's response shape, including a
   ``[SECURITY_BLOCKED] reason=...`` marker when the LearnFlowAI security
   layer blocks the request.
6. Appends a JSONL record to ``reports/<run-id>/provider-events.jsonl``
   so reports can be cross-referenced with Langfuse / SIEM traces.

Hermetic boundary: only stdlib + httpx + pydantic. No imports from
``app.*`` / ``backend.*`` / etc. — provider talks to the backend exclusively
over HTTP/SSE.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT_SECONDS = 120.0
TOKEN_REFRESH_SLACK_SECONDS = 60
SSE_DATA_PREFIX = "data:"
TERMINAL_EVENT_TYPES = frozenset({"done", "error", "security_block"})


class ProviderEvent(BaseModel):
    """One record in provider-events.jsonl. Bridges Promptfoo and LearnFlowAI."""

    run_id: str
    timestamp: str
    test_case_id: str | None = None
    plugin_id: str | None = None
    strategy_id: str | None = None
    project_id: str | None = None
    chat_id: str | None = None
    blocked: bool = False
    block_reason: str | None = None
    errored: bool = False
    error_detail: dict[str, Any] | None = None
    latency_ms: float
    prompt: str
    output: str
    sse_event_count: int = 0
    sse_event_types: list[str] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    """Runtime configuration loaded from LEARNFLOW_SCAN_* env vars."""

    base_url: str = DEFAULT_BASE_URL
    username: str
    password: str
    run_id: str
    report_dir: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    sanitize_logs: bool = False

    @classmethod
    def from_env(cls) -> ProviderConfig:
        username = os.getenv("LEARNFLOW_SCAN_USERNAME")
        password = os.getenv("LEARNFLOW_SCAN_PASSWORD")
        if not username or not password:
            raise RuntimeError(
                "LEARNFLOW_SCAN_USERNAME and LEARNFLOW_SCAN_PASSWORD must be set "
                "(see tools/security-scan/.env.example)."
            )

        run_id = os.getenv("LEARNFLOW_SCAN_RUN_ID") or datetime.now(UTC).strftime(
            "%Y-%m-%d-%H%M%S"
        )

        report_dir_env = os.getenv("LEARNFLOW_SCAN_REPORT_DIR")
        if report_dir_env:
            report_dir = Path(report_dir_env)
        else:
            report_dir = Path(__file__).parent / "reports" / run_id

        return cls(
            base_url=os.getenv("LEARNFLOW_BASE_URL") or DEFAULT_BASE_URL,
            username=username,
            password=password,
            run_id=run_id,
            report_dir=report_dir,
            timeout_seconds=float(
                os.getenv("LEARNFLOW_SCAN_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS
            ),
            sanitize_logs=(
                (os.getenv("LEARNFLOW_SCAN_SANITIZE_LOGS") or "false").lower() == "true"
            ),
        )


# Force resolution of forward references for `Path`. Required when the provider
# is loaded by Promptfoo's Python worker outside our uv venv — that interpreter
# may use a pydantic build that does not auto-rebuild models with `__future__`
# annotations.
ProviderConfig.model_rebuild()
ProviderEvent.model_rebuild()


class RateLimitedAuthError(RuntimeError):
    """Hit /api/auth/login rate limit. Do not retry — login is 5/60s per user+IP."""


def _b64decode_segment(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _parse_jwt_exp(access_token: str) -> int:
    """Decode JWT payload (no signature check) and return ``exp`` as unix seconds."""

    parts = access_token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT (expected 3 segments)")
    payload = json.loads(_b64decode_segment(parts[1]))
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("JWT payload missing integer exp")
    return exp


class LearnflowProvider:
    """Per-process provider singleton. Promptfoo reuses one instance across calls."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig.from_env()
        self._client = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout_seconds,
            follow_redirects=False,
        )
        self._access_token: str | None = None
        self._access_token_exp: int = 0
        self._project_id: uuid.UUID | None = None
        self._config.report_dir.mkdir(parents=True, exist_ok=True)
        self._event_log_path = self._config.report_dir / "provider-events.jsonl"

    def close(self) -> None:
        self._client.close()

    # ---- Auth ---------------------------------------------------------

    def _ensure_session(self) -> None:
        if self._access_token is not None:
            self._refresh_if_stale()
            return
        self._login_or_register()

    def _login_or_register(self) -> None:
        payload = {"name": self._config.username, "password": self._config.password}
        login_resp = self._client.post("/api/auth/login", json=payload)
        if login_resp.status_code == 200:
            self._set_token(str(login_resp.json()["access_token"]))
            return
        if login_resp.status_code == 429:
            retry_after = login_resp.headers.get("Retry-After", "?")
            raise RateLimitedAuthError(
                f"login rate-limited, retry after {retry_after}s — "
                "wait or check LEARNFLOW_SCAN_USERNAME/PASSWORD"
            )
        if login_resp.status_code != 401:
            raise RuntimeError(
                f"login failed with unexpected status {login_resp.status_code}: "
                f"{login_resp.text}"
            )

        register_resp = self._client.post("/api/auth/register", json=payload)
        if register_resp.status_code in (200, 201):
            self._set_token(str(register_resp.json()["access_token"]))
            return
        if register_resp.status_code == 409:
            raise RuntimeError(
                "Username already exists but login failed with 401. "
                "Check LEARNFLOW_SCAN_PASSWORD. Do NOT retry — login rate limit is 5/60s."
            )
        raise RuntimeError(
            f"register failed with status {register_resp.status_code}: "
            f"{register_resp.text}"
        )

    def _refresh_if_stale(self) -> None:
        if self._access_token is None:
            return
        if time.time() + TOKEN_REFRESH_SLACK_SECONDS < self._access_token_exp:
            return
        resp = self._client.post("/api/auth/refresh")
        if resp.status_code == 200:
            self._set_token(str(resp.json()["access_token"]))
            return
        # Refresh failed — fall back to a fresh login. This can happen if the
        # backend restarted and lost the refresh cookie.
        self._access_token = None
        self._login_or_register()

    def _set_token(self, access_token: str) -> None:
        self._access_token = access_token
        self._access_token_exp = _parse_jwt_exp(access_token)

    def _auth_headers(self) -> dict[str, str]:
        if self._access_token is None:
            raise RuntimeError("auth headers requested before session was established")
        return {"Authorization": f"Bearer {self._access_token}"}

    # ---- Project / chat ----------------------------------------------

    def _ensure_project(self) -> uuid.UUID:
        if self._project_id is not None:
            return self._project_id
        self._ensure_session()
        name = f"promptfoo-redteam-{self._config.run_id}"
        resp = self._client.post(
            "/api/projects",
            headers=self._auth_headers(),
            json={"name": name},
        )
        resp.raise_for_status()
        self._project_id = uuid.UUID(resp.json()["id"])
        return self._project_id

    def _create_chat(self, project_id: uuid.UUID) -> uuid.UUID:
        self._ensure_session()
        resp = self._client.post(
            f"/api/projects/{project_id}/chats",
            headers=self._auth_headers(),
            json={},
        )
        resp.raise_for_status()
        return uuid.UUID(resp.json()["thread_id"])

    # ---- SSE ----------------------------------------------------------

    def _stream_message(
        self, project_id: uuid.UUID, chat_id: uuid.UUID, content: str
    ) -> tuple[str, bool, str | None, bool, dict[str, Any] | None, list[str]]:
        """Send the message and consume SSE.

        Returns:
            output, blocked, block_reason, errored, error_detail, event_types
        """

        self._ensure_session()
        url = f"/api/projects/{project_id}/chats/{chat_id}/messages"
        headers = {**self._auth_headers(), "Accept": "text/event-stream"}

        text_chunks: list[str] = []
        event_types: list[str] = []
        blocked = False
        block_reason: str | None = None
        errored = False
        error_detail: dict[str, Any] | None = None

        with self._client.stream(
            "POST", url, headers=headers, json={"content": content}
        ) as response:
            if response.status_code == 403:
                # Thread already blocked — should not happen because we create
                # a fresh chat per call, but surface it loudly if it does.
                response.read()
                raise RuntimeError(
                    f"received 403 on /messages for chat {chat_id}; "
                    "fresh chats should never be pre-blocked. "
                    "Check that _create_chat is called per test case."
                )
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith(SSE_DATA_PREFIX):
                    continue
                payload_str = line[len(SSE_DATA_PREFIX) :].strip()
                if not payload_str:
                    continue
                payload: dict[str, Any] = json.loads(payload_str)
                event_type = str(payload.pop("type", ""))
                event_types.append(event_type)

                if event_type == "text_chunk":
                    chunk = payload.get("content")
                    if isinstance(chunk, str):
                        text_chunks.append(chunk)
                elif event_type == "security_block":
                    blocked = True
                    reason = payload.get("reason")
                    block_reason = str(reason) if reason is not None else None
                    break
                elif event_type == "error":
                    errored = True
                    error_detail = dict(payload)
                    break
                elif event_type == "done":
                    break
                # Other event types (tool_start/end, artifact_created,
                # final_output_review_*, trace_id) are recorded in
                # event_types but do not contribute to output.

        if blocked:
            output = f"[SECURITY_BLOCKED] reason={block_reason or 'unknown'}"
        elif errored:
            output = ""
        else:
            output = "".join(text_chunks)

        return output, blocked, block_reason, errored, error_detail, event_types

    # ---- Public entry ------------------------------------------------

    def call_api(
        self,
        prompt: str,
        options: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        del options  # Promptfoo provider options not used by this provider.

        test_case_id, plugin_id, strategy_id = _extract_test_metadata(context)

        project_id = self._ensure_project()
        started = time.monotonic()

        try:
            chat_id = self._create_chat(project_id)
            output, blocked, block_reason, errored, error_detail, event_types = (
                self._stream_message(project_id, chat_id, prompt)
            )
        except (httpx.HTTPError, RuntimeError) as exc:
            latency_ms = (time.monotonic() - started) * 1000.0
            error_payload = {
                "type": exc.__class__.__name__,
                "message": str(exc),
            }
            self._append_event(
                ProviderEvent(
                    run_id=self._config.run_id,
                    timestamp=datetime.now(UTC).isoformat(),
                    test_case_id=test_case_id,
                    plugin_id=plugin_id,
                    strategy_id=strategy_id,
                    project_id=str(project_id),
                    chat_id=None,
                    blocked=False,
                    block_reason=None,
                    errored=True,
                    error_detail=error_payload,
                    latency_ms=latency_ms,
                    prompt=self._maybe_sanitize(prompt),
                    output="",
                    sse_event_count=0,
                    sse_event_types=[],
                )
            )
            return {"error": str(exc), "metadata": {"errorDetail": error_payload}}

        latency_ms = (time.monotonic() - started) * 1000.0

        self._append_event(
            ProviderEvent(
                run_id=self._config.run_id,
                timestamp=datetime.now(UTC).isoformat(),
                test_case_id=test_case_id,
                plugin_id=plugin_id,
                strategy_id=strategy_id,
                project_id=str(project_id),
                chat_id=str(chat_id),
                blocked=blocked,
                block_reason=block_reason,
                errored=errored,
                error_detail=error_detail,
                latency_ms=latency_ms,
                prompt=self._maybe_sanitize(prompt),
                output=self._maybe_sanitize(output),
                sse_event_count=len(event_types),
                sse_event_types=event_types,
            )
        )

        if errored:
            return {
                "error": (error_detail or {}).get("detail") or "stream error",
                "metadata": {
                    "blocked": False,
                    "errored": True,
                    "errorDetail": error_detail,
                    "chatId": str(chat_id),
                    "projectId": str(project_id),
                    "latencyMs": latency_ms,
                },
            }

        return {
            "output": output,
            "metadata": {
                "blocked": blocked,
                "blockReason": block_reason,
                "chatId": str(chat_id),
                "projectId": str(project_id),
                "runId": self._config.run_id,
                "latencyMs": latency_ms,
                "sseEventTypes": event_types,
            },
        }

    # ---- Internals ----------------------------------------------------

    def _append_event(self, event: ProviderEvent) -> None:
        with self._event_log_path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json())
            fh.write("\n")

    def _maybe_sanitize(self, text: str) -> str:
        if not self._config.sanitize_logs:
            return text
        if len(text) <= 200:
            return text
        return text[:200] + f"... [truncated, total {len(text)} chars]"


def _extract_test_metadata(
    context: dict[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    if not context:
        return None, None, None
    test = context.get("test") if isinstance(context.get("test"), dict) else None
    metadata = (
        test.get("metadata")
        if isinstance(test, dict) and isinstance(test.get("metadata"), dict)
        else None
    )
    if metadata is None:
        return None, None, None
    test_case_id = metadata.get("testCaseId") or metadata.get("test_case_id")
    plugin_id = metadata.get("pluginId") or metadata.get("plugin_id")
    strategy_id = metadata.get("strategyId") or metadata.get("strategy_id")
    return (
        str(test_case_id) if test_case_id is not None else None,
        str(plugin_id) if plugin_id is not None else None,
        str(strategy_id) if strategy_id is not None else None,
    )


_provider: LearnflowProvider | None = None


def _get_provider() -> LearnflowProvider:
    global _provider
    if _provider is None:
        _provider = LearnflowProvider()
    return _provider


def call_api(
    prompt: str,
    options: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promptfoo Python provider entry point."""

    return _get_provider().call_api(prompt, options, context)


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "Usage: python learnflow_provider.py <prompt>\n"
            "Standalone smoke mode for tools/security-scan/learnflow_provider.py.\n"
            "Reads LEARNFLOW_SCAN_* env vars (load .env first).",
            file=sys.stderr,
        )
        return 2
    prompt = argv[1]
    result = call_api(prompt)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv))
