"""Smoke test: pandas/numpy computation rendered to a PNG via matplotlib.

Exercises the scientific-Python slice of the job toolchain baked into the
executor image (design-brief § Executor: "реальные задачи, не
import-проверки") — not just that the packages import, but that a real
plot renders and the output is a genuine PNG. Backend is selected via the
`MPLBACKEND=Agg` env var `run_all.sh` exports (no display in the container);
this script assumes it is already set rather than mutating `os.environ`
before importing matplotlib (avoids an import-after-statement ordering
hack).
"""

import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# pandas ships no bundled py.typed marker (pandas-stubs is a separate,
# unlisted dependency) — same class of issue as root pyproject.toml's
# pdfkit/mdx_math/fuzzysearch overrides; kept as a local ignore since a
# [[tool.mypy.overrides]] entry would touch a file outside T3.7's scope
# (services/executor/** + Makefile).
import pandas as pd  # type: ignore[import-untyped]
from _common import report

NAME = "matplotlib_png"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def main() -> None:
    df = pd.DataFrame({"x": np.linspace(0, 10, 200)})
    df["y"] = np.sin(df["x"]) * np.exp(-df["x"] / 5)

    fig, ax = plt.subplots()
    ax.plot(df["x"], df["y"])
    ax.set_title("smoke: pandas/numpy -> matplotlib")

    with tempfile.TemporaryDirectory(prefix="smoke-mpl-") as tmpdir:
        png_path = Path(tmpdir) / "smoke.png"
        fig.savefig(png_path, format="png")
        plt.close(fig)

        size = png_path.stat().st_size
        if size == 0:
            raise AssertionError("PNG output is empty")

        magic = png_path.read_bytes()[: len(_PNG_MAGIC)]
        if magic != _PNG_MAGIC:
            raise AssertionError(f"unexpected PNG magic bytes: {magic!r}")


if __name__ == "__main__":
    report(NAME, main)
