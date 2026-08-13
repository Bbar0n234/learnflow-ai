"""Log output of the executor: JSON lines, honoured level, readable tracebacks.

The executor is a headless internal service — when a job misbehaves the only
thing an operator has is its stdout, so the log line has to survive the trip:
one JSON object per event, filtered at the configured level, and a failure to
launch a job carrying an actual traceback rather than a boolean flag.
"""

from __future__ import annotations

import json

import pytest
import structlog
from executor.logging import configure_logging


def _emitted(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.strip()]


@pytest.mark.unit
def test_configure_logging_emits_json_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("info")

    structlog.get_logger().info("job finished", exit_code=0)

    events = _emitted(capsys)
    assert len(events) == 1
    assert events[0]["event"] == "job finished"
    assert events[0]["exit_code"] == 0
    assert events[0]["level"] == "info"
    assert "timestamp" in events[0]


@pytest.mark.unit
def test_configure_logging_filters_below_the_configured_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("warning")

    logger = structlog.get_logger()
    logger.info("job finished")
    logger.warning("timeout clamped")

    assert [event["event"] for event in _emitted(capsys)] == ["timeout clamped"]


@pytest.mark.unit
def test_configure_logging_renders_exception_tracebacks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`exc_info=True` has to come out as a traceback, not as `true`.

    The one place the executor logs at ERROR is a job that could not be started
    at all; without traceback rendering that line says only "something raised",
    which is exactly the case where the operator has nothing else to go on.
    """
    configure_logging("info")

    try:
        raise RuntimeError("bwrap not found")
    except RuntimeError:
        structlog.get_logger().error("job launch failed", exc_info=True)

    event = _emitted(capsys)[0]
    assert "exc_info" not in event
    assert "Traceback (most recent call last)" in str(event["exception"])
    assert "RuntimeError: bwrap not found" in str(event["exception"])


@pytest.mark.unit
def test_configure_logging_rejects_an_unknown_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A typo in `EXECUTOR_LOG_LEVEL` stops the service instead of guessing.

    Silently falling back would leave an operator convinced they had raised the
    verbosity while the service kept its old level.
    """
    with pytest.raises(KeyError):
        configure_logging("chatty")
