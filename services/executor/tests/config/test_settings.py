"""The `EXECUTOR_*` knobs — names, defaults and the prefix that binds them.

These names are a contract with the deployment side: the same eight knobs live
in `docker-compose.yml` and both `.env*.example` files, written by another
track. A renamed field or a changed default would not fail anything at startup —
the service would just quietly run on its own defaults while operations believed
the compose value applied — so the defaults are asserted literally and the
prefix is asserted to be the only thing the service listens to.
"""

from __future__ import annotations

import pytest
from executor.config import Settings


@pytest.mark.unit
def test_settings_defaults_match_the_documented_knobs() -> None:
    """Every default is the one the plan's knob table publishes."""
    settings = Settings()

    assert settings.workspaces_root == "/workspaces"
    assert settings.skills_root == "/skills"
    assert settings.default_timeout_seconds == 60
    assert settings.max_timeout_seconds == 300
    assert settings.max_output_bytes == 262144
    assert settings.kill_grace_seconds == 5
    assert settings.log_level == "info"


@pytest.mark.unit
def test_settings_sandbox_is_enabled_unless_explicitly_disabled() -> None:
    """The escape hatch has to be opened deliberately.

    Compose never sets this knob, so its default *is* the production value —
    defaulting to `False` would run every job unsandboxed on a service whose
    entire purpose is isolation.
    """
    assert Settings().sandbox_enabled is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env_var", "attribute", "raw", "expected"),
    [
        ("EXECUTOR_WORKSPACES_ROOT", "workspaces_root", "/data/ws", "/data/ws"),
        ("EXECUTOR_SKILLS_ROOT", "skills_root", "/mnt/skills", "/mnt/skills"),
        ("EXECUTOR_DEFAULT_TIMEOUT_SECONDS", "default_timeout_seconds", "30", 30),
        ("EXECUTOR_MAX_TIMEOUT_SECONDS", "max_timeout_seconds", "42", 42),
        ("EXECUTOR_MAX_OUTPUT_BYTES", "max_output_bytes", "4096", 4096),
        ("EXECUTOR_KILL_GRACE_SECONDS", "kill_grace_seconds", "9", 9),
        ("EXECUTOR_LOG_LEVEL", "log_level", "debug", "debug"),
        ("EXECUTOR_SANDBOX_ENABLED", "sandbox_enabled", "false", False),
    ],
)
def test_settings_reads_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    attribute: str,
    raw: str,
    expected: object,
) -> None:
    monkeypatch.setenv(env_var, raw)

    assert getattr(Settings(), attribute) == expected


@pytest.mark.unit
def test_settings_ignores_unprefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare `LOG_LEVEL` belongs to another service, not to this one."""
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("MAX_TIMEOUT_SECONDS", "1")

    settings = Settings()

    assert settings.log_level == "info"
    assert settings.max_timeout_seconds == 300
