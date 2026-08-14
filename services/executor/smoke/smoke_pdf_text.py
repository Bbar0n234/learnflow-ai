"""Smoke test: text extraction from a PDF via pypdf.

Uses a small, deterministic fixture (`fixtures/sample.pdf`, checked into the
repo) rather than generating a PDF on the fly — the point of this scenario
is verifying the *extraction* leg of the toolchain (design-brief § A12:
"агент сам извлёк текст (job) и работал с ним"), not PDF authoring, and a
fixture is more deterministic than any generator this script could carry.
"""

from pathlib import Path

import pypdf
from _common import report

NAME = "pdf_text"

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"
_MARKER = "SMOKE_PDF_MARKER"


def main() -> None:
    if not _FIXTURE.is_file():
        raise AssertionError(f"fixture missing: {_FIXTURE}")

    reader = pypdf.PdfReader(str(_FIXTURE))
    text = "".join(page.extract_text() or "" for page in reader.pages)

    if _MARKER not in text:
        raise AssertionError(
            f"marker {_MARKER!r} not found in extracted text: {text!r}"
        )


if __name__ == "__main__":
    report(NAME, main)
