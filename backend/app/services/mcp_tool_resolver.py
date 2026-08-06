from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import SSEConnection, StreamableHttpConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.mcp_server import ProjectMCPServer, ThreadMCPServer, UserMCPServer
from app.repositories.mcp_server import MCPServerRepository
from app.services.encryption import EncryptionService
from app.services.url_validator import mcp_no_redirect_client_factory, validate_url

logger = structlog.get_logger()

MAX_USER_TOOLS = 20
CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache key: (user_id, project_id, thread_id) as strings
_CacheKey = tuple[str, str, str]

_SCOPE_INDEX = {"user": 0, "project": 1, "thread": 2}


class MCPToolResolver:
    """Resolves user MCP tools from DB servers with caching, dedup, and resource limits."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        encryption_service: EncryptionService,
        global_tool_names: set[str],
        mcp_timeout: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._encryption = encryption_service
        self._global_tool_names = global_tool_names
        self._mcp_timeout = mcp_timeout
        self._cache: dict[_CacheKey, tuple[list[BaseTool], float]] = {}

    async def resolve(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> list[BaseTool]:
        """Resolve user MCP tools via additive merge: thread ∪ project ∪ user.

        Returns deduplicated tools list (max MAX_USER_TOOLS).
        Cached for CACHE_TTL_SECONDS per scope combination.
        """
        key: _CacheKey = (str(user_id), str(project_id), str(thread_id))

        cached = self._cache.get(key)
        if cached is not None:
            tools, timestamp = cached
            if time.monotonic() - timestamp < CACHE_TTL_SECONDS:
                return tools

        try:
            tools = await self._resolve_uncached(user_id, project_id, thread_id)
        except Exception:
            logger.warning("mcp tool resolution failed", exc_info=True)
            tools = []

        self._cache[key] = (tools, time.monotonic())
        return tools

    async def _resolve_uncached(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> list[BaseTool]:
        async with self._session_factory() as session:
            repo = MCPServerRepository(session)

            thread_servers = await repo.list_by_thread(thread_id, active_only=True)
            project_servers = await repo.list_by_project(project_id, active_only=True)
            user_servers = await repo.list_by_user(user_id, active_only=True)

            # Collect disabled server IDs from cascade overrides
            project_disabled = await repo.list_disabled_ids("project", project_id)
            thread_disabled = await repo.list_disabled_ids("thread", thread_id)
            disabled_ids = project_disabled | thread_disabled

        # Collect tools with priority: thread > project > user
        seen_names: set[str] = set()
        all_tools: list[BaseTool] = []

        scope_groups: list[tuple[list[Any], str]] = [
            (thread_servers, "thread"),
            (project_servers, "project"),
            (user_servers, "user"),
        ]
        for servers, scope_name in scope_groups:
            for server in servers:
                if server.id in disabled_ids:
                    continue
                try:
                    server_tools = await self._fetch_tools(server)
                    for tool in server_tools:
                        if tool.name in seen_names:
                            continue
                        if tool.name in self._global_tool_names:
                            continue
                        seen_names.add(tool.name)
                        all_tools.append(tool)
                except Exception:
                    logger.warning(
                        "mcp server unreachable",
                        server_name=server.name,
                        scope=scope_name,
                        exc_info=True,
                    )

        if len(all_tools) > MAX_USER_TOOLS:
            logger.warning(
                "user tools truncated to limit",
                total=len(all_tools),
                limit=MAX_USER_TOOLS,
            )
            all_tools = all_tools[:MAX_USER_TOOLS]

        if all_tools:
            logger.info(
                "mcp tools loaded",
                tool_count=len(all_tools),
                tool_names=[t.name for t in all_tools],
            )

        return all_tools

    async def _fetch_tools(
        self,
        server: UserMCPServer | ProjectMCPServer | ThreadMCPServer,
    ) -> list[BaseTool]:
        """Fetch tools from a single MCP server with connection-time SSRF check."""
        # Connection-time SSRF validation (defense in depth)
        validate_url(server.url)

        headers: dict[str, Any] = {}
        if server.api_key_encrypted and self._encryption.is_available:
            api_key = self._encryption.decrypt(server.api_key_encrypted)
            headers["Authorization"] = f"Bearer {api_key}"

        conn: SSEConnection | StreamableHttpConnection
        if server.transport == "sse":
            conn = SSEConnection(
                transport="sse",
                url=server.url,
                sse_read_timeout=float(self._mcp_timeout),
                httpx_client_factory=mcp_no_redirect_client_factory,
            )
            if headers:
                conn["headers"] = headers
        else:
            # StreamableHttpConnection.timeout expects timedelta; passing int is
            # accepted at runtime but mismatches the TypedDict annotation.
            conn = StreamableHttpConnection(
                transport="streamable_http",
                url=server.url,
                timeout=self._mcp_timeout,  # type: ignore[typeddict-item]
                httpx_client_factory=mcp_no_redirect_client_factory,
            )
            if headers:
                conn["headers"] = headers

        client = MultiServerMCPClient({server.name: conn})
        tools = await client.get_tools(server_name=server.name)

        # Filter by allowed_tools if configured
        if server.allowed_tools:
            allowed = set(server.allowed_tools)
            tools = [t for t in tools if t.name in allowed]

        return tools

    def invalidate(self, scope_type: str, scope_id: uuid.UUID) -> None:
        """Invalidate cache entries matching a scope.

        Called on MCP server CRUD operations. Targeted: only entries
        containing the given scope_id are removed.
        """
        idx = _SCOPE_INDEX.get(scope_type)
        if idx is None:
            return
        sid = str(scope_id)
        keys_to_remove = [k for k in self._cache if k[idx] == sid]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(
            "mcp tool cache invalidated",
            scope=scope_type,
            scope_id=sid,
            cleared=len(keys_to_remove),
        )
