"""Service facade for MCP server mutations with full metadata validation.

Security invariants enforced here for every CRUD entry-point:
remote ``tools/list`` fetch → ``SecurityGuard.check(Checkpoint.MCP_METADATA)``
against the full blob → SSRF validation → API-key encryption → persistence.
Unreachable hosts are fail-closed (HTTP 503). Update paths revalidate only
when mutable surface (``url`` / ``transport`` / ``allowed_tools`` / ``name``
/ reactivate) changes.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import structlog
from fastapi import HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import SSEConnection, StreamableHttpConnection

from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, Verdict
from app.api.schemas.mcp_servers import MCPServerCreate, MCPServerUpdate
from app.repositories.mcp_server import MCPServerRepository
from app.services.encryption import EncryptionService
from app.services.url_validator import validate_url

logger = structlog.get_logger()

Scope = Literal["user", "project", "thread"]

_TEXT_SCHEMA_KEYS = frozenset({"description", "title", "examples", "default", "enum"})


def _build_test_connection(
    url: str, transport: str, api_key: str | None
) -> SSEConnection | StreamableHttpConnection:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    if transport == "sse":
        conn_sse = SSEConnection(transport="sse", url=url, sse_read_timeout=30)
        if headers:
            conn_sse["headers"] = headers
        return conn_sse
    conn_http = StreamableHttpConnection(
        transport="streamable_http",
        url=url,
        timeout=30,  # type: ignore[typeddict-item]
    )
    if headers:
        conn_http["headers"] = headers
    return conn_http


async def fetch_remote_metadata(
    url: str, transport: str, api_key: str | None
) -> list[dict[str, Any]]:
    """Fetch ``tools/list`` from a remote MCP server.

    Returns a list of ``{name, description, inputSchema}`` dicts. Raises on
    connectivity / protocol errors — callers map to 503.
    """
    conn = _build_test_connection(url, transport, api_key)
    client = MultiServerMCPClient({"_validate": conn})
    tools = await client.get_tools(server_name="_validate")

    result: list[dict[str, Any]] = []
    for tool in tools:
        schema = getattr(tool, "args_schema", None) or getattr(
            tool, "input_schema", None
        )
        schema_dict: Any
        if schema is not None and hasattr(schema, "model_json_schema"):
            schema_dict = schema.model_json_schema()
        elif isinstance(schema, dict):
            schema_dict = schema
        else:
            schema_dict = {}
        result.append(
            {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", "") or "",
                "inputSchema": schema_dict,
            }
        )
    return result


def extract_schema_text(schema: Any) -> str:
    """Recursively collect text-valued fields from a JSON Schema.

    Signal/noise balance: the attack surface we care about is *natural
    language* in schema descriptions and examples, not type constraints.
    Types / ``required`` / numeric bounds are skipped.
    """
    parts: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _TEXT_SCHEMA_KEYS:
                    if isinstance(value, str):
                        parts.append(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                parts.append(item)
                            elif isinstance(item, dict):
                                _walk(item)
                    elif isinstance(value, dict):
                        _walk(value)
                elif isinstance(value, (dict, list)):
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema or {})
    return "\n".join(p.strip() for p in parts if p and p.strip())


def serialize_mcp_meta_blob(
    *,
    name: str,
    transport: str,
    url: str,
    allowed_tools: list[str],
    remote_tools: list[dict[str, Any]],
) -> str:
    """Deterministic serialization of MCP metadata for guard inspection."""
    sections: list[str] = [
        f"name: {name}",
        f"transport: {transport}",
        f"url: {url}",
        f"allowed_tools: {', '.join(allowed_tools or [])}",
    ]
    for tool in remote_tools:
        schema_text = extract_schema_text(tool.get("inputSchema"))
        sections.append(
            "\n".join(
                filter(
                    None,
                    [
                        f"tool.name: {tool.get('name', '')}",
                        f"tool.description: {tool.get('description', '')}",
                        f"tool.schema_text:\n{schema_text}" if schema_text else "",
                    ],
                )
            )
        )
    return "\n---\n".join(sections)


class McpServerService:
    def __init__(
        self,
        repo: MCPServerRepository,
        guard: SecurityGuard | None,
        encryption: EncryptionService,
    ) -> None:
        self._repo = repo
        self._guard = guard
        self._encryption = encryption

    async def guard_and_persist(
        self,
        *,
        scope: Scope,
        owner_id: uuid.UUID,
        payload: MCPServerCreate,
    ) -> Any:
        """Fetch remote tools, run guard on the full blob, persist."""
        plaintext_api_key = getattr(payload, "api_key", None)
        url_str = str(payload.url)

        remote_tools = await self._fetch_or_503(
            url=url_str,
            transport=payload.transport,
            api_key=plaintext_api_key,
        )

        await self._guard_blob(
            scope=scope,
            owner_id=owner_id,
            name=payload.name,
            transport=payload.transport,
            url=url_str,
            allowed_tools=payload.allowed_tools or [],
            remote_tools=remote_tools,
        )

        data = self._validate_and_encrypt(payload)

        if scope == "user":
            data["user_id"] = owner_id
            return await self._repo.create_user_server(**data)
        if scope == "project":
            data["project_id"] = owner_id
            return await self._repo.create_project_server(**data)
        data["thread_id"] = owner_id
        return await self._repo.create_thread_server(**data)

    async def update_and_reguard(
        self,
        *,
        scope: Scope,
        owner_id: uuid.UUID,
        server: Any,
        payload: MCPServerUpdate,
    ) -> Any:
        """Apply a PUT, revalidating only when mutable surface changes.

        Revalidation rules:
        - ``url`` / ``transport`` / ``allowed_tools`` / ``name`` changed → full flow.
        - Reactivation (``is_active`` false → true) → full flow.
        - ``api_key`` only / deactivation → skip revalidation.
        """
        data = self._apply_update_fields(server, payload)

        revalidate = self._needs_revalidation(server, payload)
        if revalidate and self._guard is not None:
            new_name = payload.name if payload.name is not None else server.name
            new_transport = (
                payload.transport if payload.transport is not None else server.transport
            )
            new_url = str(payload.url) if payload.url is not None else server.url
            new_allowed = (
                payload.allowed_tools
                if payload.allowed_tools is not None
                else (server.allowed_tools or [])
            )
            api_key_plain = getattr(payload, "api_key", None)
            if (
                not api_key_plain
                and server.api_key_encrypted
                and self._encryption.is_available
            ):
                api_key_plain = self._encryption.decrypt(server.api_key_encrypted)

            remote_tools = await self._fetch_or_503(
                url=new_url,
                transport=new_transport,
                api_key=api_key_plain,
            )
            await self._guard_blob(
                scope=scope,
                owner_id=owner_id,
                name=new_name,
                transport=new_transport,
                url=new_url,
                allowed_tools=new_allowed,
                remote_tools=remote_tools,
            )

        if data:
            server = await self._repo.update(server, **data)
        return server

    # -------------------------------------------------------------- helpers

    async def _fetch_or_503(
        self, *, url: str, transport: str, api_key: str | None
    ) -> list[dict[str, Any]]:
        try:
            validate_url(url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        try:
            return await fetch_remote_metadata(url, transport, api_key)
        except Exception as exc:
            logger.warning("mcp remote metadata fetch failed", url=url, error=str(exc))
            raise HTTPException(
                status_code=503,
                detail={"error": "mcp_unreachable", "reason": str(exc)},
            ) from None

    async def _guard_blob(
        self,
        *,
        scope: Scope,
        owner_id: uuid.UUID,
        name: str,
        transport: str,
        url: str,
        allowed_tools: list[str],
        remote_tools: list[dict[str, Any]],
    ) -> None:
        if self._guard is None:
            return
        blob = serialize_mcp_meta_blob(
            name=name,
            transport=transport,
            url=url,
            allowed_tools=allowed_tools,
            remote_tools=remote_tools,
        )
        result = await self._guard.check(
            blob,
            Checkpoint.MCP_METADATA,
            trace_ctx={
                "top_level": True,
                "user_id": str(owner_id),
                "scope": f"mcp.{scope}",
            },
        )
        if result.verdict == Verdict.INJECTION:
            logger.warning(
                "mcp metadata injection blocked",
                security_event=True,
                checkpoint=Checkpoint.MCP_METADATA.value,
                verdict=Verdict.INJECTION.value,
                user_id=str(owner_id),
                scope=scope,
                detection_layer=(
                    result.detection_layer.value if result.detection_layer else None
                ),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "security_policy_violation",
                    "reason": (
                        result.detection_layer.value
                        if result.detection_layer
                        else "mcp_metadata"
                    ),
                },
            )

    @staticmethod
    def _needs_revalidation(server: Any, payload: MCPServerUpdate) -> bool:
        if payload.name is not None and payload.name != server.name:
            return True
        if payload.transport is not None and payload.transport != server.transport:
            return True
        if payload.url is not None and str(payload.url) != server.url:
            return True
        if payload.allowed_tools is not None and payload.allowed_tools != (
            server.allowed_tools or []
        ):
            return True
        return payload.is_active is True and getattr(server, "is_active", True) is False

    def _apply_update_fields(
        self, server: Any, payload: MCPServerUpdate
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}

        if payload.url is not None:
            url_str = str(payload.url)
            try:
                validate_url(url_str)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from None
            data["url"] = url_str
        if payload.name is not None:
            data["name"] = payload.name
        if payload.transport is not None:
            data["transport"] = payload.transport
        if payload.allowed_tools is not None:
            data["allowed_tools"] = payload.allowed_tools
        if payload.is_active is not None:
            data["is_active"] = payload.is_active

        api_key = getattr(payload, "api_key", None)
        if api_key is not None:
            if api_key == "":
                data["api_key_encrypted"] = None
                data["api_key_hint"] = None
            else:
                if not self._encryption.is_available:
                    raise HTTPException(
                        status_code=400,
                        detail="MCP_ENCRYPTION_KEY not configured, cannot store API keys",
                    )
                data["api_key_encrypted"] = self._encryption.encrypt(api_key)
                data["api_key_hint"] = (
                    f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                )
        return data

    def _validate_and_encrypt(self, body: MCPServerCreate) -> dict[str, Any]:
        data: dict[str, Any] = {}

        url_str = str(body.url)
        try:
            validate_url(url_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        data["url"] = url_str

        data["name"] = body.name
        data["transport"] = body.transport
        if body.allowed_tools is not None:
            data["allowed_tools"] = body.allowed_tools

        api_key = getattr(body, "api_key", None)
        if api_key:
            if not self._encryption.is_available:
                raise HTTPException(
                    status_code=400,
                    detail="MCP_ENCRYPTION_KEY not configured, cannot store API keys",
                )
            data["api_key_encrypted"] = self._encryption.encrypt(api_key)
            data["api_key_hint"] = (
                f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
            )

        return data
