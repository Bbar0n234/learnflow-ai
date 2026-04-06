import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.agent.config import load_agent_config
from app.agent.graph_factory import GraphFactory
from app.agent.runner import LangGraphAgentRunner
from app.agent.tools import (
    ks_tools,
    make_create_artifact_tool,
    make_load_skill_tool,
    scan_skills_index,
    user_memory_tools,
)
from app.api.routes import (
    artifacts,
    auth,
    chats,
    feedback,
    mcp_servers,
    messages,
    models,
    projects,
    sphere,
    user_memory,
)
from app.api.routes import settings as settings_routes
from app.config import Settings
from app.infra.db import create_engine, create_session_factory
from app.infra.langfuse import (
    ensure_model_definitions,
    init_langfuse,
    shutdown_langfuse,
)
from app.infra.langgraph import create_checkpointer, create_store
from app.infra.logging import setup_logging
from app.infra.mcp import create_mcp_client
from app.infra.prompt_provider import PromptProvider
from app.infra.redis import create_redis
from app.services.encryption import EncryptionService
from app.services.exceptions import EntityNotFoundError
from app.services.mcp_tool_resolver import MCPToolResolver
from app.services.model_config_resolver import ModelConfigResolver

logger = structlog.get_logger()


def _content_hash(text: str, config: dict[str, Any]) -> str:
    return hashlib.sha256(
        (text + json.dumps(config, sort_keys=True)).encode()
    ).hexdigest()


def _load_prompt_config(agent_config: Any, name: str) -> dict[str, Any]:
    if name == "system":
        return {
            "model": agent_config.llm.model,
            "extra_body": agent_config.llm.extra_body,
        }
    if name == "summarization" and agent_config.summarization:
        return {
            "model": agent_config.summarization.model,
            "max_tokens": agent_config.summarization.max_summary_tokens,
        }
    return {}


def _seed_prompts(
    langfuse: Any,
    prompts_dir: Path,
    agent_config: Any,
    label: str,
) -> None:
    """Seed prompts to Langfuse on startup (idempotent, duplicate-safe).

    Prompt names are qualified with label: "system--development", "system--production".
    This gives full isolation between environments — each has its own version history.
    Dedup compares file content against all versions of the qualified prompt.
    """
    for prompt_name in ["system", "summarization"]:
        file_path = prompts_dir / f"{prompt_name}.txt"
        if not file_path.exists():
            continue

        qualified = f"{prompt_name}--{label}"
        file_text = file_path.read_text(encoding="utf-8")
        file_config = _load_prompt_config(agent_config, prompt_name)
        file_hash = _content_hash(file_text, file_config)

        try:
            meta = langfuse.api.prompts.list(name=qualified)
            if not meta.data:
                langfuse.create_prompt(
                    name=qualified,
                    prompt=file_text,
                    config=file_config,
                )
                logger.info("prompt seeded", name=qualified)
                continue

            all_versions = meta.data[0].versions
            is_duplicate = any(
                _content_hash(
                    langfuse.get_prompt(qualified, version=v).prompt,
                    langfuse.get_prompt(qualified, version=v).config,
                )
                == file_hash
                for v in all_versions
            )
            if not is_duplicate:
                langfuse.create_prompt(
                    name=qualified,
                    prompt=file_text,
                    config=file_config,
                )
                logger.info("prompt synced", name=qualified)
        except Exception:
            logger.warning("prompt seed/sync failed", name=prompt_name, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()

    setup_logging(
        log_level=settings.log_level,
        config_path=Path(__file__).resolve().parents[2] / "configs" / "logging.yaml",
        log_file=settings.log_file,
    )

    try:
        init_langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
        )
    except Exception:
        logger.warning(
            "langfuse init failed, proceeding without tracing", exc_info=True
        )

    agent_config = load_agent_config()

    try:
        ensure_model_definitions(agent_config.models)
    except Exception:
        logger.warning("langfuse model definitions init failed", exc_info=True)

    logger.debug(
        "loaded config",
        log_level=settings.log_level,
        cors_origins=settings.cors_origins,
        llm_base_url=settings.llm_base_url,
    )
    logger.info("app started")

    engine = create_engine(settings)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    app.state.redis = await create_redis(settings)

    # PromptProvider
    prompts_dir = Path(__file__).resolve().parents[2] / "configs" / "prompts"
    langfuse_client = None
    from app.infra.langfuse import langfuse_enabled

    if langfuse_enabled:
        from langfuse import get_client

        langfuse_client = get_client()

    prompt_provider = PromptProvider(
        langfuse=langfuse_client,
        label=settings.langfuse_prompt_label,
        cache_ttl=settings.langfuse_prompt_cache_ttl,
        prompts_dir=prompts_dir,
    )
    app.state.prompt_provider = prompt_provider

    # Seed prompts to Langfuse
    if langfuse_client:
        _seed_prompts(
            langfuse_client, prompts_dir, agent_config, settings.langfuse_prompt_label
        )

    # Encryption service
    encryption_service = EncryptionService(settings.mcp_encryption_key)
    app.state.encryption_service = encryption_service

    # LangGraph persistence
    lg_db_url = settings.langgraph_database_url
    async with (
        create_store(lg_db_url) as store,
        create_checkpointer(lg_db_url) as checkpointer,
    ):
        await store.setup()
        await checkpointer.setup()

        app.state.store = store
        app.state.checkpointer = checkpointer

        # Tools
        skills_dir = Path(__file__).resolve().parents[2] / "skills"
        load_skill = make_load_skill_tool(skills_dir)
        skills_idx = scan_skills_index(skills_dir)
        create_artifact = make_create_artifact_tool(app.state.session_factory)

        # MCP external tools (graceful degradation)
        mcp_tools: list = []
        try:
            mcp_client = create_mcp_client(agent_config.mcp_servers)
            if mcp_client is not None:
                for server_name, server_config in agent_config.mcp_servers.items():
                    if not server_config.enabled:
                        continue
                    tools = await mcp_client.get_tools(server_name=server_name)
                    if server_config.allowed_tools:
                        allowed = set(server_config.allowed_tools)
                        tools = [t for t in tools if t.name in allowed]
                    mcp_tools.extend(tools)
                enabled = sum(1 for s in agent_config.mcp_servers.values() if s.enabled)
                logger.info(
                    "mcp tools loaded",
                    tool_count=len(mcp_tools),
                    servers_active=enabled,
                    servers_total=len(agent_config.mcp_servers),
                )
        except Exception:
            logger.warning(
                "mcp tools init failed, starting without external tools",
                exc_info=True,
            )

        global_tools = (
            ks_tools + user_memory_tools + [load_skill, create_artifact] + mcp_tools
        )

        # GraphFactory + ModelConfigResolver
        graph_factory = GraphFactory(
            settings=settings,
            agent_config=agent_config,
            global_tools=global_tools,
            skills_index=skills_idx,
            checkpointer=checkpointer,
            store=store,
            prompt_provider=prompt_provider,
        )

        model_resolver = ModelConfigResolver(
            prompt_provider=prompt_provider,
            agent_config=agent_config,
        )

        # MCPToolResolver for user MCP servers
        global_tool_names = {t.name for t in global_tools}
        tool_resolver = MCPToolResolver(
            session_factory=app.state.session_factory,
            encryption_service=encryption_service,
            global_tool_names=global_tool_names,
        )

        app.state.tool_resolver = tool_resolver

        app.state.agent_runner = LangGraphAgentRunner(
            graph_factory=graph_factory,
            model_resolver=model_resolver,
            checkpointer=checkpointer,
            tool_resolver=tool_resolver,
        )
        app.state.agent_config = agent_config

        yield

    shutdown_langfuse()
    if app.state.redis:
        await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="LearnFlowAI", lifespan=lifespan)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        structlog.contextvars.clear_contextvars()
        request_id = str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        return response

    # Exception handlers
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: object, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # Health check
    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    # API routes
    api_prefix = "/api"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(chats.router, prefix=api_prefix)
    app.include_router(messages.router, prefix=api_prefix)
    app.include_router(artifacts.router, prefix=api_prefix)
    app.include_router(sphere.router, prefix=api_prefix)
    app.include_router(feedback.router, prefix=api_prefix)
    app.include_router(models.router, prefix=api_prefix)
    app.include_router(settings_routes.router, prefix=api_prefix)
    app.include_router(user_memory.router, prefix=api_prefix)
    app.include_router(mcp_servers.router, prefix=api_prefix)

    # Serve frontend static files (only when dist exists — Docker mode)
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dir.exists():
        frontend_resolved = frontend_dir.resolve()

        app.mount(
            "/assets",
            StaticFiles(directory=str(frontend_resolved / "assets")),
            name="assets",
        )

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str) -> FileResponse:
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            file_path = (frontend_resolved / full_path).resolve()
            if file_path.is_file() and file_path.is_relative_to(frontend_resolved):
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_resolved / "index.html"))

    return app


app = create_app()
