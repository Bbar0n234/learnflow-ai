import os
from typing import Any

import structlog
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import (
    SSEConnection,
    StdioConnection,
    StreamableHttpConnection,
    WebsocketConnection,
)

from app.agent.config import MCPServerConfig

logger = structlog.get_logger()

type _Connection = (
    StdioConnection | SSEConnection | StreamableHttpConnection | WebsocketConnection
)


def _resolve_headers(cfg: MCPServerConfig) -> dict[str, Any] | None:
    """Resolve Authorization header from env var if configured."""
    if not cfg.api_key_env:
        return None
    api_key = os.environ.get(cfg.api_key_env, "")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    logger.warning(
        "mcp server env var not set, skipping auth header",
        env_var=cfg.api_key_env,
    )
    return None


def _build_connection(cfg: MCPServerConfig, timeout: int) -> _Connection:
    """Build a typed connection dict from MCPServerConfig."""
    transport = cfg.transport

    if transport == "stdio":
        if not cfg.command:
            raise ValueError("MCP server: stdio transport requires 'command'")
        conn = StdioConnection(
            transport="stdio",
            command=cfg.command,
            args=cfg.args or [],
        )
        return conn

    headers = _resolve_headers(cfg)
    if not cfg.url:
        raise ValueError(f"MCP server: {transport} transport requires 'url'")

    if transport == "sse":
        conn_sse = SSEConnection(
            transport="sse", url=cfg.url, sse_read_timeout=float(timeout)
        )
        if headers:
            conn_sse["headers"] = headers
        return conn_sse

    # "http" → streamable_http (alias per langchain-mcp-adapters docs).
    # StreamableHttpConnection.timeout expects timedelta; passing int is accepted
    # at runtime but mismatches the TypedDict annotation.
    conn_http = StreamableHttpConnection(
        transport="streamable_http",
        url=cfg.url,
        timeout=timeout,  # type: ignore[typeddict-item]
    )
    if headers:
        conn_http["headers"] = headers
    return conn_http


def build_mcp_connections(
    servers: dict[str, MCPServerConfig],
    timeout: int,
) -> dict[str, _Connection]:
    """Convert MCPServerConfig dict → MultiServerMCPClient connections dict.

    Skips servers with enabled=false.
    """
    return {
        name: _build_connection(cfg, timeout)
        for name, cfg in servers.items()
        if cfg.enabled
    }


def create_mcp_client(
    servers: dict[str, MCPServerConfig],
    timeout: int,
) -> MultiServerMCPClient | None:
    """Create MultiServerMCPClient from config. Returns None if no servers configured."""
    if not servers:
        return None
    connections = build_mcp_connections(servers, timeout)
    return MultiServerMCPClient(connections)
