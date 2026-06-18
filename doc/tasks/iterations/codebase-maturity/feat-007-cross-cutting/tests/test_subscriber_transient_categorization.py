"""T4.13 fix — subscriber transient-vs-poison categorization predicate.

Stand finding F-SIEM-T4.13: when the SIEM DB is fully down, asyncpg/uvloop
raises a raw builtin ConnectionRefusedError ([Errno 111]) at connect time. It is
NOT wrapped into sqlalchemy.exc.OperationalError, so the old
`except (OperationalError, DBAPIError)` barrier missed it — the subscriber task
crashed and `siem_events_transient` never incremented.

The fix routes the decision through the pure predicate
`is_transient_db_error`. These tests pin its categorization without a live DB:
connect-time / connection-level failures are transient (keep in PEL, no crash),
ValidationError (poison) and unexpected bugs are NOT transient (must NOT be
swallowed as transient).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SIEM_JWT_SECRET", "test-secret")

# conftest.py adds backend/; add siem-service/ so `siem_service.*` resolves.
_ROOT = Path(__file__).resolve().parents[6]
_SIEM_DIR = _ROOT / "services" / "siem-service"
if str(_SIEM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIEM_DIR))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from siem_contracts import SecurityEvent  # noqa: E402
from sqlalchemy.exc import DBAPIError, OperationalError  # noqa: E402

from siem_service.pipeline.subscriber import is_transient_db_error  # noqa: E402


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionRefusedError(111, "Connection refused"),  # the real F-SIEM-T4.13 case
        ConnectionResetError("reset"),
        ConnectionError("generic connection error"),
        BrokenPipeError("broken pipe"),
        OperationalError("stmt", {}, Exception("dropped mid-statement")),
        DBAPIError("stmt", {}, Exception("dbapi")),
    ],
)
def test_connect_and_db_errors_are_transient(exc: BaseException) -> None:
    assert is_transient_db_error(exc) is True


def test_validation_error_is_not_transient() -> None:
    """Poison (schema-invalid event) must NOT be treated as transient."""
    with pytest.raises(ValidationError) as exc_info:
        SecurityEvent.model_validate({"not": "a valid security event"})
    assert is_transient_db_error(exc_info.value) is False


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("unexpected bug"),
        KeyError("missing"),
        FileNotFoundError("not a connection failure"),  # OSError but not transient
        PermissionError("not a connection failure"),  # OSError but not transient
    ],
)
def test_unexpected_and_unrelated_os_errors_are_not_transient(
    exc: BaseException,
) -> None:
    """Unexpected bugs and non-connection OSErrors must bubble up, not be swallowed."""
    assert is_transient_db_error(exc) is False
