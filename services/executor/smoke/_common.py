"""Shared PASS/FAIL reporting helper for the executor image smoke scripts.

Each `smoke_*.py` script defines a `main()` that either returns normally
(scenario passed) or raises (scenario failed — the exception message becomes
the failure reason). `report()` turns that into the one-line `PASS <name>` /
`FAIL <name>: <reason>` contract `run_all.sh` relies on, plus a matching
process exit code (T3.7 plan: "каждый [сценарий]: ненулевой exit при
провале, вывод в одну строку PASS/FAIL <имя>").
"""

import sys
import traceback
from collections.abc import Callable


def report(name: str, main: Callable[[], None]) -> None:
    """Run `main`, print the PASS/FAIL line, and exit with the matching code."""
    try:
        main()
    except Exception as exc:
        print(f"FAIL {name}: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    else:
        print(f"PASS {name}")
        sys.exit(0)
