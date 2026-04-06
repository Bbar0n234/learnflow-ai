from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import SSEConnection, StreamableHttpConnection

from app.api.deps import CurrentUser, DBSession, UserProject
from app.api.schemas.mcp_servers import (
    InheritedMCPServer,
    MCPServerCreate,
    MCPServerListResponse,
    MCPServerResponse,
    MCPServerUpdate,
    TestConnectionResponse,
    ToggleInheritedRequest,
)
from app.models.mcp_server import (
    ProjectMCPServer,
    ThreadMCPServer,
    UserMCPServer,
)
from app.repositories.mcp_server import MCPServerRepository
from app.services.encryption import EncryptionService
from app.services.url_validator import validate_url

logger = structlog.get_logger()

router = APIRouter(tags=["mcp-servers"])

MAX_SERVERS_PER_SCOPE = 5


def _get_encryption(request: Request) -> EncryptionService:
    return request.app.state.encryption_service


def _get_tool_resolver(request: Request) -> Any:
    return request.app.state.tool_resolver


def _to_response(
    server: UserMCPServer | ProjectMCPServer | ThreadMCPServer,
) -> MCPServerResponse:
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        transport=server.transport,
        url=server.url,
        has_api_key=server.api_key_encrypted is not None,
        api_key_hint=server.api_key_hint,
        allowed_tools=server.allowed_tools or [],
        is_active=server.is_active,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _to_inherited(
    server: UserMCPServer | ProjectMCPServer | ThreadMCPServer,
    disabled_ids: set[uuid.UUID],
) -> InheritedMCPServer:
    return InheritedMCPServer(
        id=server.id,
        name=server.name,
        transport=server.transport,
        url=server.url,
        has_api_key=server.api_key_encrypted is not None,
        api_key_hint=server.api_key_hint,
        is_active=server.is_active,
        is_disabled=server.id in disabled_ids,
    )


def _validate_and_encrypt(
    body: MCPServerCreate | MCPServerUpdate,
    encryption: EncryptionService,
) -> dict:
    """Validate URL, encrypt API key, return data dict for DB."""
    data: dict = {}

    url = getattr(body, "url", None)
    if url is not None:
        url_str = str(url)
        try:
            validate_url(url_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        data["url"] = url_str

    if hasattr(body, "name") and body.name is not None:
        data["name"] = body.name
    if hasattr(body, "transport") and body.transport is not None:
        data["transport"] = body.transport
    if hasattr(body, "allowed_tools") and body.allowed_tools is not None:
        data["allowed_tools"] = body.allowed_tools
    if hasattr(body, "is_active") and body.is_active is not None:
        data["is_active"] = body.is_active

    api_key = getattr(body, "api_key", None)
    if api_key is not None:
        if api_key == "":
            data["api_key_encrypted"] = None
            data["api_key_hint"] = None
        else:
            if not encryption.is_available:
                raise HTTPException(
                    status_code=400,
                    detail="MCP_ENCRYPTION_KEY not configured, cannot store API keys",
                )
            data["api_key_encrypted"] = encryption.encrypt(api_key)
            data["api_key_hint"] = (
                f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
            )

    return data


async def _test_connection(
    url: str, transport: str, api_key: str | None
) -> TestConnectionResponse:
    """Test MCP server connection."""
    try:
        validate_url(url)
    except ValueError as e:
        return TestConnectionResponse(success=False, error=str(e))

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        conn: SSEConnection | StreamableHttpConnection
        if transport == "sse":
            conn = SSEConnection(transport="sse", url=url, sse_read_timeout=30)
            if headers:
                conn["headers"] = headers
        else:
            conn = StreamableHttpConnection(
                transport="streamable_http",
                url=url,
                timeout=30,  # type: ignore[typeddict-item]
            )
            if headers:
                conn["headers"] = headers

        client = MultiServerMCPClient({"test": conn})
        tools = await client.get_tools(server_name="test")
        tool_names = [t.name for t in tools]
        return TestConnectionResponse(success=True, tools=tool_names)
    except Exception as e:
        logger.warning("mcp test connection failed", url=url, error=str(e))
        return TestConnectionResponse(
            success=False,
            error="Connection failed: server is unreachable or returned an error",
        )


# ====================== User-level ======================


@router.get("/users/me/mcp-servers", response_model=MCPServerListResponse)
async def list_user_servers(
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> MCPServerListResponse:
    repo = MCPServerRepository(session)
    servers = await repo.list_by_user(user.id, active_only=False)
    return MCPServerListResponse(items=[_to_response(s) for s in servers])


@router.post("/users/me/mcp-servers", response_model=MCPServerResponse, status_code=201)
async def create_user_server(
    body: MCPServerCreate,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    count = await repo.count_by_scope("user", user.id)
    if count >= MAX_SERVERS_PER_SCOPE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SERVERS_PER_SCOPE} servers per scope",
        )
    data = _validate_and_encrypt(body, enc)
    data["user_id"] = user.id
    server = await repo.create_user_server(**data)
    _get_tool_resolver(request).invalidate("user", user.id)
    return _to_response(server)


@router.put("/users/me/mcp-servers/{server_id}", response_model=MCPServerResponse)
async def update_user_server(
    server_id: uuid.UUID,
    body: MCPServerUpdate,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_user_server(server_id)
    if server is None or server.user_id != user.id:
        raise HTTPException(status_code=404, detail="Server not found")
    data = _validate_and_encrypt(body, enc)
    if data:
        server = await repo.update(server, **data)
    _get_tool_resolver(request).invalidate("user", user.id)
    return _to_response(server)


@router.delete("/users/me/mcp-servers/{server_id}", status_code=204)
async def delete_user_server(
    server_id: uuid.UUID,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> None:
    repo = MCPServerRepository(session)
    server = await repo.get_user_server(server_id)
    if server is None or server.user_id != user.id:
        raise HTTPException(status_code=404, detail="Server not found")
    await repo.cleanup_disables_for_server(server_id)
    await repo.delete(server)
    _get_tool_resolver(request).invalidate("user", user.id)


@router.post(
    "/users/me/mcp-servers/{server_id}/test",
    response_model=TestConnectionResponse,
)
async def test_user_server(
    server_id: uuid.UUID,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> TestConnectionResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_user_server(server_id)
    if server is None or server.user_id != user.id:
        raise HTTPException(status_code=404, detail="Server not found")
    api_key = None
    if server.api_key_encrypted and enc.is_available:
        api_key = enc.decrypt(server.api_key_encrypted)
    return await _test_connection(server.url, server.transport, api_key)


# ====================== Project-level ======================


@router.get("/projects/{project_id}/mcp-servers", response_model=MCPServerListResponse)
async def list_project_servers(
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
    include_inherited: bool = False,
) -> MCPServerListResponse:
    repo = MCPServerRepository(session)
    servers = await repo.list_by_project(project.id, active_only=False)
    inherited: list[InheritedMCPServer] = []
    if include_inherited:
        user_servers = await repo.list_by_user(user.id, active_only=False)
        disabled_ids = await repo.list_disabled_ids("project", project.id)
        inherited = [_to_inherited(s, disabled_ids) for s in user_servers]
    return MCPServerListResponse(
        items=[_to_response(s) for s in servers],
        inherited=inherited,
    )


@router.post(
    "/projects/{project_id}/mcp-servers",
    response_model=MCPServerResponse,
    status_code=201,
)
async def create_project_server(
    body: MCPServerCreate,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    count = await repo.count_by_scope("project", project.id)
    if count >= MAX_SERVERS_PER_SCOPE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SERVERS_PER_SCOPE} servers per scope",
        )
    data = _validate_and_encrypt(body, enc)
    data["project_id"] = project.id
    server = await repo.create_project_server(**data)
    _get_tool_resolver(request).invalidate("project", project.id)
    return _to_response(server)


@router.put(
    "/projects/{project_id}/mcp-servers/{server_id}",
    response_model=MCPServerResponse,
)
async def update_project_server(
    server_id: uuid.UUID,
    body: MCPServerUpdate,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_project_server(server_id)
    if server is None or server.project_id != project.id:
        raise HTTPException(status_code=404, detail="Server not found")
    data = _validate_and_encrypt(body, enc)
    if data:
        server = await repo.update(server, **data)
    _get_tool_resolver(request).invalidate("project", project.id)
    return _to_response(server)


@router.delete("/projects/{project_id}/mcp-servers/{server_id}", status_code=204)
async def delete_project_server(
    server_id: uuid.UUID,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> None:
    repo = MCPServerRepository(session)
    server = await repo.get_project_server(server_id)
    if server is None or server.project_id != project.id:
        raise HTTPException(status_code=404, detail="Server not found")
    await repo.cleanup_disables_for_server(server_id)
    await repo.delete(server)
    _get_tool_resolver(request).invalidate("project", project.id)


@router.post(
    "/projects/{project_id}/mcp-servers/{server_id}/test",
    response_model=TestConnectionResponse,
)
async def test_project_server(
    server_id: uuid.UUID,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> TestConnectionResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_project_server(server_id)
    if server is None or server.project_id != project.id:
        raise HTTPException(status_code=404, detail="Server not found")
    api_key = None
    if server.api_key_encrypted and enc.is_available:
        api_key = enc.decrypt(server.api_key_encrypted)
    return await _test_connection(server.url, server.transport, api_key)


# ====================== Project-level toggle ======================


@router.put(
    "/projects/{project_id}/mcp-servers/inherited/{server_id}/toggle",
)
async def toggle_project_inherited(
    server_id: uuid.UUID,
    body: ToggleInheritedRequest,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> dict[str, bool]:
    repo = MCPServerRepository(session)
    await repo.set_disable("project", project.id, server_id, disabled=body.disabled)
    _get_tool_resolver(request).invalidate("project", project.id)
    return {"disabled": body.disabled}


# ====================== Thread-level ======================


@router.get(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers",
    response_model=MCPServerListResponse,
)
async def list_thread_servers(
    thread_id: uuid.UUID,
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
    include_inherited: bool = False,
) -> MCPServerListResponse:
    repo = MCPServerRepository(session)
    servers = await repo.list_by_thread(thread_id, active_only=False)
    inherited: list[InheritedMCPServer] = []
    if include_inherited:
        user_servers = await repo.list_by_user(user.id, active_only=False)
        project_servers = await repo.list_by_project(project.id, active_only=False)
        disabled_ids = await repo.list_disabled_ids("thread", thread_id)
        all_inherited: list[UserMCPServer | ProjectMCPServer] = [
            *user_servers,
            *project_servers,
        ]
        inherited = [_to_inherited(s, disabled_ids) for s in all_inherited]
    return MCPServerListResponse(
        items=[_to_response(s) for s in servers],
        inherited=inherited,
    )


@router.post(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers",
    response_model=MCPServerResponse,
    status_code=201,
)
async def create_thread_server(
    thread_id: uuid.UUID,
    body: MCPServerCreate,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    count = await repo.count_by_scope("thread", thread_id)
    if count >= MAX_SERVERS_PER_SCOPE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SERVERS_PER_SCOPE} servers per scope",
        )
    data = _validate_and_encrypt(body, enc)
    data["thread_id"] = thread_id
    server = await repo.create_thread_server(**data)
    _get_tool_resolver(request).invalidate("thread", thread_id)
    return _to_response(server)


@router.put(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers/{server_id}",
    response_model=MCPServerResponse,
)
async def update_thread_server(
    server_id: uuid.UUID,
    thread_id: uuid.UUID,
    body: MCPServerUpdate,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> MCPServerResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_thread_server(server_id)
    if server is None or server.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Server not found")
    data = _validate_and_encrypt(body, enc)
    if data:
        server = await repo.update(server, **data)
    _get_tool_resolver(request).invalidate("thread", thread_id)
    return _to_response(server)


@router.delete(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers/{server_id}",
    status_code=204,
)
async def delete_thread_server(
    server_id: uuid.UUID,
    thread_id: uuid.UUID,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> None:
    repo = MCPServerRepository(session)
    server = await repo.get_thread_server(server_id)
    if server is None or server.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Server not found")
    await repo.cleanup_disables_for_server(server_id)
    await repo.delete(server)
    _get_tool_resolver(request).invalidate("thread", thread_id)


@router.post(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers/{server_id}/test",
    response_model=TestConnectionResponse,
)
async def test_thread_server(
    server_id: uuid.UUID,
    thread_id: uuid.UUID,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> TestConnectionResponse:
    repo = MCPServerRepository(session)
    enc = _get_encryption(request)
    server = await repo.get_thread_server(server_id)
    if server is None or server.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Server not found")
    api_key = None
    if server.api_key_encrypted and enc.is_available:
        api_key = enc.decrypt(server.api_key_encrypted)
    return await _test_connection(server.url, server.transport, api_key)


@router.put(
    "/projects/{project_id}/chats/{thread_id}/mcp-servers/inherited/{server_id}/toggle",
)
async def toggle_thread_inherited(
    server_id: uuid.UUID,
    thread_id: uuid.UUID,
    body: ToggleInheritedRequest,
    project: UserProject,
    session: DBSession,
    request: Request,
) -> dict[str, bool]:
    repo = MCPServerRepository(session)
    await repo.set_disable("thread", thread_id, server_id, disabled=body.disabled)
    _get_tool_resolver(request).invalidate("thread", thread_id)
    return {"disabled": body.disabled}
