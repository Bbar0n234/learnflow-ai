"""feat-005: init_langfuse() returns enabled flag (no module-global).

The changed contract (pkt 5): init returns bool instead of setting a global, so
the caller injects the flag into instrumentation.
"""

from types import SimpleNamespace

import app.infra.langfuse as lf


def test_no_keys_returns_false() -> None:
    assert lf.init_langfuse(public_key="", secret_key="", host="http://lf") is False


def test_auth_failure_returns_false(monkeypatch) -> None:
    monkeypatch.setattr(lf, "Langfuse", lambda **kw: SimpleNamespace())
    monkeypatch.setattr(
        lf, "get_client", lambda: SimpleNamespace(auth_check=lambda: False)
    )
    assert (
        lf.init_langfuse(public_key="pk", secret_key="sk", host="http://lf") is False
    )


def test_success_returns_true(monkeypatch) -> None:
    score_configs = SimpleNamespace(
        get=lambda limit: SimpleNamespace(data=[]),
        create=lambda **kw: None,
    )
    client = SimpleNamespace(
        auth_check=lambda: True,
        api=SimpleNamespace(score_configs=score_configs),
    )
    monkeypatch.setattr(lf, "Langfuse", lambda **kw: SimpleNamespace())
    monkeypatch.setattr(lf, "get_client", lambda: client)
    assert lf.init_langfuse(public_key="pk", secret_key="sk", host="http://lf") is True


def test_ensure_helpers_skip_when_disabled() -> None:
    # No client interaction when disabled — must not raise.
    lf.ensure_security_score_config(enabled=False)
    lf.ensure_model_definitions([], enabled=False)
