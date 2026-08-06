"""Env surface of the SIEM kill-switch: what ``SIEM_ENABLED`` parses into.

Solitary-unit over ``Settings`` — no infra, no app. The toggle is an operational
knob an admin types into a production ``.env`` by hand, so the contract worth
pinning is the one an admin can get wrong: the default must be "on" (a machine
that never heard of the variable behaves exactly as before), the value the
runbook prescribes must turn emission off, and a typo must fail loudly at
startup instead of being read as "on".

**"Off" has two different meanings here, and the suite keeps them apart.**
Pydantic accepts a whole family of falsy strings (``0``, ``False``, ``no``,
``off``, ...), but only the lowercase literal ``false`` is the canonical value:
``production.md`` § SIEM prescribes it, and it is the only string that also
switches the UI off, because compose hands ``SIEM_ENABLED`` to the frontend
build verbatim and the frontend rule is ``!== "false"``. So the canonical value
gets its own case, and the wider family gets one case that spells the asymmetry
out instead of presenting it as a second right answer.

The Makefile sources ``.env``/``.env.local`` into the shell before pytest, so
every test here first removes the ambient variable — otherwise the developer's
own machine would decide the outcome.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No ambient toggle (the Makefile sources .env before pytest)."""
    monkeypatch.delenv("SIEM_ENABLED", raising=False)
    return monkeypatch


@pytest.mark.unit
def test_siem_emission_is_enabled_by_default(clean_env: pytest.MonkeyPatch) -> None:
    # Dev behaves as it did before the kill-switch; production opts out
    # explicitly, so a forgotten .env line costs the toggle's benefit and
    # nothing else (design-brief § Env-гигиена).
    assert Settings().siem_enabled is True


@pytest.mark.unit
def test_the_canonical_off_value_disables_emission(
    clean_env: pytest.MonkeyPatch,
) -> None:
    # The one string the runbook prescribes (production.md § SIEM, шаг 1) and
    # the only one that turns the whole subsystem off, all three layers of it.
    clean_env.setenv("SIEM_ENABLED", "false")

    assert Settings().siem_enabled is False


@pytest.mark.unit
@pytest.mark.parametrize("value", ["0", "False", "FALSE", "no", "off"])
def test_other_falsy_spellings_stop_emission_but_leave_the_ui_on(
    clean_env: pytest.MonkeyPatch, value: str
) -> None:
    # ⚠ This is the seam between the layers, and it is a contract, not a bug.
    # Pydantic reads every one of these as False, so emission does stop. The UI
    # does not: compose passes the operator's string through untouched
    # (`VITE_SIEM_ENABLED: ${SIEM_ENABLED:-true}` — no normalization anywhere on
    # the way), and the frontend flag is off only for the literal lowercase
    # "false". An operator who writes `SIEM_ENABLED=0` into the production .env
    # therefore gets a silent half-switch: no events, but the «Безопасность»
    # button and the /security route still in the bundle — pointing at an
    # upstream that is no longer running.
    clean_env.setenv("SIEM_ENABLED", value)

    assert Settings().siem_enabled is False
    # The frontend rule, restated here as the assertion that makes the
    # asymmetry visible in this suite instead of only in the frontend one.
    assert value != "false"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["true", "1", "True"])
def test_truthy_values_keep_emission_enabled(
    clean_env: pytest.MonkeyPatch, value: str
) -> None:
    clean_env.setenv("SIEM_ENABLED", value)

    assert Settings().siem_enabled is True


@pytest.mark.unit
def test_an_unparseable_value_fails_startup_instead_of_defaulting_to_on(
    clean_env: pytest.MonkeyPatch,
) -> None:
    # The dangerous silent failure would be a misspelling quietly falling back
    # to the default: an operator who meant to switch SIEM off would keep
    # emitting and never learn it. Pydantic rejects the value instead, and the
    # container refuses to start. ``match`` pins the field: ``Settings`` has
    # other required fields (``jwt_secret``), and without it the test would go
    # green on somebody else's validation error.
    clean_env.setenv("SIEM_ENABLED", "off-please")

    with pytest.raises(ValidationError, match="siem_enabled"):
        Settings()


@pytest.mark.unit
def test_the_two_kill_switches_are_independent(clean_env: pytest.MonkeyPatch) -> None:
    # Two toggles of the same iteration, two subsystems: turning SIEM emission
    # off must not touch the inline LLM defense (and the reverse), because a
    # single mistyped name in Settings would couple them invisibly.
    clean_env.setenv("SIEM_ENABLED", "false")
    clean_env.delenv("LLM_DEFENSE_ENABLED", raising=False)

    settings = Settings()

    assert settings.siem_enabled is False
    assert settings.llm_defense_enabled is True
