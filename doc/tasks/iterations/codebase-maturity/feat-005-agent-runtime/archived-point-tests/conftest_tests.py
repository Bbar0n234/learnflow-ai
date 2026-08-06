"""Shared pytest setup for feat-005 point tests.

Clears proxy env vars before any ``ChatOpenAI`` client is constructed: the
underlying httpx client otherwise picks up a SOCKS proxy from the environment
and fails on the missing ``socksio`` extra. Tests here never make network
calls, so dropping proxies is safe and keeps construction offline.
"""

import os

for _var in (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
):
    os.environ.pop(_var, None)
