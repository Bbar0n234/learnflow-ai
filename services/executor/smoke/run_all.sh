#!/bin/bash
# Sequential smoke run for the executor image — release gate (design-brief
# § Executor "Смоук-набор образа как процесс"; T3.7 plan). Runs every
# scenario below (does not stop at the first failure — an aggregated result
# is more useful for diagnosing a broken image than a truncated run), prints
# an aggregated summary, and exits non-zero if any scenario failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXECUTOR_ROOT="$(dirname "${SCRIPT_DIR}")"

# smoke_sandbox.py imports `executor.*` — the package isn't pip-installed
# into the shared venv (same PYTHONPATH convention the rest of the repo uses
# for standalone scripts, e.g. `backend/scripts/*` run with `PYTHONPATH=.`).
export PYTHONPATH="${EXECUTOR_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
# Headless backend — no display in the container.
export MPLBACKEND="Agg"

scenarios=(
    "${SCRIPT_DIR}/smoke_matplotlib_png.py"
    "${SCRIPT_DIR}/smoke_pandoc_docx.sh"
    "${SCRIPT_DIR}/smoke_pdf_text.py"
    "${SCRIPT_DIR}/smoke_python_docx.py"
    "${SCRIPT_DIR}/smoke_fonts.py"
    "${SCRIPT_DIR}/smoke_sandbox.py"
)

run_scenario() {
    case "$1" in
        *.sh) bash "$1" ;;
        *.py) python3 "$1" ;;
        *)
            echo "run_all: unknown scenario type: $1" >&2
            return 1
            ;;
    esac
}

failures=0
for scenario in "${scenarios[@]}"; do
    run_scenario "${scenario}" || failures=$((failures + 1))
done

echo "----"
if [ "${failures}" -gt 0 ]; then
    echo "run_all: ${failures}/${#scenarios[@]} scenario(s) failed"
    exit 1
fi

echo "run_all: all ${#scenarios[@]} scenarios passed"
