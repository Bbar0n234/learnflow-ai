"""Test-package bootstrap: the shared secret must exist before any import.

`executor.main` builds its app at import time (`app = create_app()` — the
uvicorn entrypoint), and `Settings.auth_token` is required with no default
(conventions.md § Секреты и fail-fast). So the variable has to be in the
environment *before* `tests/conftest.py` imports `executor.main`, which rules
out setting it inside conftest — pytest imports this package first.

`setdefault`, not `setenv`: a developer running the suite with a real
`EXECUTOR_AUTH_TOKEN` exported keeps it here, and `conftest._clean_executor_env`
pins the value per test anyway.
"""

import os

# Value every fixture and every auth test speaks; imported by conftest.
AUTH_TOKEN = "test-executor-token"

os.environ.setdefault("EXECUTOR_AUTH_TOKEN", AUTH_TOKEN)
