"""Smoke test: font coverage for the job toolchain.

Two legs: `fc-match` resolves DejaVu/Noto (the families the image's apt layer
installs — Dockerfile `fonts-dejavu`/`fonts-noto-core`, matched via
`fontconfig`), and matplotlib renders a Cyrillic title without emitting a
missing-glyph warning (the actual glyph coverage a job would hit rendering a
chart with Russian labels, not just "the package is importable"). Backend
is `Agg`, selected via the `MPLBACKEND` env var `run_all.sh` exports.
"""

import subprocess
import warnings

import matplotlib.pyplot as plt
from _common import report

NAME = "fonts"

_EXPECTED_FAMILIES = ("DejaVu Sans", "Noto Sans")


def _check_fc_match(family: str) -> None:
    result = subprocess.run(
        ["fc-match", family],
        capture_output=True,
        text=True,
        check=True,
    )
    matched = result.stdout.strip()
    if not matched:
        raise AssertionError(f"fc-match returned nothing for {family!r}")
    if family.split()[0].lower() not in matched.lower():
        raise AssertionError(
            f"fc-match for {family!r} resolved to unrelated font: {matched!r}"
        )


def _check_cyrillic_render() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = plt.subplots()
        ax.set_title("Проверка кириллицы: заголовок графика 123")
        fig.canvas.draw()
        plt.close(fig)

    glyph_warnings = [w for w in caught if "glyph" in str(w.message).lower()]
    if glyph_warnings:
        messages = [str(w.message) for w in glyph_warnings]
        raise AssertionError(
            f"missing-glyph warnings while rendering Cyrillic: {messages}"
        )


def main() -> None:
    for family in _EXPECTED_FAMILIES:
        _check_fc_match(family)
    _check_cyrillic_render()


if __name__ == "__main__":
    report(NAME, main)
