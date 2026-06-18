"""
conftest.py for T3 point tests.

Adds the backend directory to sys.path so that `app.*` imports resolve.
These tests are archived in the iteration artifact directory (not in backend/tests/).
"""

import sys
from pathlib import Path

# Add backend/ to sys.path so that 'app' and 'siem_contracts' are importable.
_BACKEND_DIR = Path(__file__).resolve().parents[6] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
