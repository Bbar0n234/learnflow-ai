"""Executor test harness: deterministic settings, in-memory ASGI client, log isolation.

The executor owns no database and no network clients, so there is nothing to
spin up here — the whole harness is (1) a `Settings` factory pinned to a
per-test temporary workspaces root, (2) an ASGI client factory over a freshly
built `create_app()`, and (3) isolation of the two pieces of global state the
service does touch: `EXECUTOR_*` environment variables and structlog's global
configuration.

Sandboxing is **off by default** in these settings: every test that actually
starts a process runs the job bare (`sandbox_enabled=False`) instead of under
`unshare`+`bwrap`. Real sandboxed execution needs unprivileged user namespaces,
which are unavailable in the agent/CI sandbox and differ per host — it is
covered by `make smoke-executor` (`smoke/smoke_sandbox.py`) and the manual
integration cases, not here. The argv that *would* be handed to `bwrap` is
asserted directly in `tests/sandbox/`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import executor.api.routes
import executor.main
import executor.runner
import executor.sandbox
import pytest
import pytest_asyncio
import structlog
from executor.api.deps import get_settings
from executor.config import Settings
from executor.main import create_app
from httpx import ASGITransport, AsyncClient


def _reset_structlog() -> None:
    """Return structlog to its default configuration and hand out fresh loggers.

    `executor.logging.configure_logging` (run by every `create_app()`, including
    the module-level one built on import) configures structlog with
    `cache_logger_on_first_use=True`. A cached bound logger keeps a reference to
    the processor list that was current when it was bound, while
    `structlog.testing.capture_logs` swaps processors in whichever list is
    configured *now* — so a logger cached under an earlier `create_app()` would
    silently escape capture, making log assertions depend on test order (and the
    negative ones — "no warning was emitted" — vacuously green).

    Rebinding each module-level proxy (every module that logs is listed here) to
    a freshly created one drops whatever it had cached without reaching into
    structlog's cache representation: a proxy returned by `get_logger()` has by
    definition not been used yet. Paired with `reset_defaults()`, every test
    starts from the same place.
    """
    structlog.reset_defaults()
    executor.api.routes.logger = structlog.get_logger()
    executor.main.logger = structlog.get_logger()
    executor.runner.logger = structlog.get_logger()
    executor.sandbox.logger = structlog.get_logger()


@pytest.fixture(autouse=True)
def _isolated_structlog() -> Iterator[None]:
    _reset_structlog()
    yield
    _reset_structlog()


@pytest.fixture(autouse=True)
def _clean_executor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop any `EXECUTOR_*` variables the developer's shell happens to export.

    `Settings()` reads the process environment, so without this a local
    `EXECUTOR_SANDBOX_ENABLED=…` would leak into every test.
    """
    for key in [key for key in os.environ if key.startswith("EXECUTOR_")]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def skills_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


@pytest.fixture
def workspace(workspaces_root: Path) -> Path:
    """An existing workspace directory for project `p1`.

    Created by the fixture, never by the executor — the service treats a missing
    workspace as a request error (design-brief § Executor: every mkdir belongs
    to the backend).
    """
    path = workspaces_root / "p1"
    path.mkdir()
    return path


@pytest.fixture
def make_settings(workspaces_root: Path, skills_root: Path) -> Callable[..., Settings]:
    """Factory for `Settings` pinned to the per-test roots.

    Timeouts are deliberately short so deadline behaviour is observable without
    making the suite slow; individual tests override what they exercise.
    """

    def _make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "workspaces_root": str(workspaces_root),
            "skills_root": str(skills_root),
            "default_timeout_seconds": 5,
            "max_timeout_seconds": 10,
            "kill_grace_seconds": 1,
            "max_output_bytes": 65536,
            "sandbox_enabled": False,
        }
        values.update(overrides)
        return Settings(**values)

    return _make


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


@pytest_asyncio.fixture
async def make_client(
    workspace: Path,
) -> AsyncIterator[Callable[[Settings], AsyncClient]]:
    """Factory of in-memory ASGI clients, one app per call.

    `create_app()` builds its own `Settings` from the environment; tests inject
    theirs through `app.dependency_overrides` on the settings provider — the
    same seam the handler uses (`SettingsDep`), so nothing about the request
    path is bypassed. Depends on `workspace` so that project `p1` exists for
    every request-level test — the executor refuses to create one itself.
    """
    clients: list[AsyncClient] = []

    def _make(settings: Settings) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://executor"
        )
        clients.append(client)
        return client

    yield _make

    for client in clients:
        await client.aclose()


@pytest.fixture
def client(
    make_client: Callable[[Settings], AsyncClient], settings: Settings
) -> AsyncClient:
    return make_client(settings)
