"""Geo resolution: solitary-unit on the fail-closed IP → country mapping.

``resolve_country`` takes the reader as an argument, so the MMDB library is
doubled by a stub at that seam — no database file is needed, and the two record
shapes the code must understand (flat IPinfo Lite, nested GeoLite2) are fed in
directly. The point of the suite is the fail-closed rule: every way the lookup
can fail — no database, a miss on a private address, an unparsable IP — must
land on the fallback country and never on "no restriction".

``open_reader`` is exercised against the real filesystem (unset path, missing
file, unreadable file); resolution against a real MMDB is a manual case, since
the database is a licensed artefact that does not live in the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.infra.geoip import open_reader, resolve_country
from maxminddb.types import Record
from structlog.testing import capture_logs

from tests.oauth._helpers import corrupt_geoip_reader
from tests.oauth._helpers import geoip_reader_for as _reader


@pytest.mark.unit
def test_open_reader_without_a_configured_path_degrades_to_none() -> None:
    with capture_logs() as logs:
        reader = open_reader("")

    assert reader is None
    assert any("geoip db path not configured" in entry["event"] for entry in logs)


@pytest.mark.unit
def test_open_reader_with_a_missing_file_degrades_to_none(tmp_path: Path) -> None:
    with capture_logs() as logs:
        reader = open_reader(str(tmp_path / "absent.mmdb"))

    assert reader is None
    assert any("not found" in entry["event"] for entry in logs)


@pytest.mark.unit
def test_open_reader_with_an_unreadable_file_degrades_to_none(tmp_path: Path) -> None:
    # A file that exists but is not an MMDB: startup must warn and continue,
    # not crash the process (the whole app boots behind this call).
    broken = tmp_path / "broken.mmdb"
    broken.write_bytes(b"not an mmdb at all")

    with capture_logs() as logs:
        reader = open_reader(str(broken))

    assert reader is None
    assert any("failed to open" in entry["event"] for entry in logs)


@pytest.mark.unit
def test_resolve_country_without_a_reader_returns_the_fallback() -> None:
    assert resolve_country(None, "8.8.8.8", "RU") == "RU"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"country_code": "US"}, "US"),  # IPinfo Lite — flat
        ({"country": {"iso_code": "US"}}, "US"),  # GeoLite2 — nested
        ({"country_code": "us"}, "US"),  # normalised to upper case
        ({"country_code": "RU", "country": {"iso_code": "US"}}, "RU"),
    ],
)
def test_resolve_country_reads_both_database_schemas(
    record: Record, expected: str
) -> None:
    assert resolve_country(_reader(record), "8.8.8.8", "XX") == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "record",
    [
        None,  # lookup miss: private/dev addresses are absent from the database
        {},
        {"country_code": ""},
        {"country": {}},
        {"country": "US"},  # unexpected shape — not a mapping
        {"country_code": 7},
        ["US"],
    ],
)
def test_resolve_country_falls_back_when_the_record_yields_no_code(
    record: Record | None,
) -> None:
    assert resolve_country(_reader(record), "127.0.0.1", "RU") == "RU"


@pytest.mark.unit
def test_resolve_country_falls_back_on_an_unparsable_ip() -> None:
    # get_client_ip returns the literal "unknown" when there is no client.
    assert resolve_country(_reader({"country_code": "US"}), "unknown", "RU") == "RU"


@pytest.mark.unit
def test_resolve_country_falls_back_on_a_corrupt_database() -> None:
    # A truncated or damaged MMDB passes open_reader (only the header is read
    # there) and blows up on the first lookup instead. That failure is another
    # way not to know the country, so it belongs on the fail-closed path: an
    # escaping exception would answer every /providers, authorize and callback
    # with a 500 rather than with the fallback country.
    assert resolve_country(corrupt_geoip_reader(), "8.8.8.8", "RU") == "RU"


@pytest.mark.unit
@pytest.mark.parametrize("configured", ["ru", " ru ", "Ru", "RU\n"])
def test_resolve_country_normalises_the_configured_fallback_to_an_iso_code(
    configured: str,
) -> None:
    # The gate compares the country strictly against "RU", so a fallback typed
    # in lower case (or with stray whitespace) in the environment must not turn
    # fail-closed inside out — all three degraded exits normalise it.
    assert resolve_country(None, "8.8.8.8", configured) == "RU"  # no database
    assert resolve_country(_reader(None), "127.0.0.1", configured) == "RU"  # miss
    assert resolve_country(_reader({}), "unknown", configured) == "RU"  # bad IP


@pytest.mark.unit
def test_resolve_country_fallback_is_the_configured_one_not_a_hardcoded_ru() -> None:
    # The fail-closed default is RU by configuration, not by code: a deployment
    # that sets another fallback must get that one on every degraded path.
    assert resolve_country(None, "8.8.8.8", "US") == "US"
    assert resolve_country(_reader(None), "127.0.0.1", "DE") == "DE"
