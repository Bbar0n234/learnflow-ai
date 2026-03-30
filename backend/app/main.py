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
from app.agent.graph import build_graph, compile_graph
from app.agent.runner import LangGraphAgentRunner
from app.agent.tools import (
    ks_tools,
    make_create_artifact_tool,
    make_load_skill_tool,
    scan_skills_index,
)
from app.api.routes import artifacts, auth, chats, feedback, messages, projects, sphere
from app.config import Settings
from app.infra.db import create_engine, create_session_factory
from app.infra.langfuse import (
    ensure_model_definitions,
    init_langfuse,
    shutdown_langfuse,
)
from app.infra.langgraph import create_checkpointer, create_store
from app.infra.llm import create_llm, create_summarization_llm
from app.infra.logging import setup_logging
from app.infra.mcp import create_mcp_client
from app.infra.redis import create_redis
from app.services.exceptions import EntityNotFoundError

logger = structlog.get_logger()


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
    # Fail-fast: verify DB is reachable at startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # Redis (trace storage for feedback persistence)
    app.state.redis = await create_redis(settings)

    # LangGraph persistence
    lg_db_url = settings.langgraph_database_url
    async with (
        create_store(lg_db_url) as store,
        create_checkpointer(lg_db_url) as checkpointer,
    ):
        await store.setup()
        await checkpointer.setup()

        app.state.store = store

        # Agent graph
        llm = create_llm(settings, agent_config)
        summarization_llm = None
        if agent_config.summarization is not None:
            summarization_llm = create_summarization_llm(
                settings, agent_config.summarization
            )

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
                    tools = await mcp_client.get_tools(server_name=server_name)
                    if server_config.allowed_tools:
                        allowed = set(server_config.allowed_tools)
                        tools = [t for t in tools if t.name in allowed]
                    mcp_tools.extend(tools)
                logger.info(
                    "mcp tools loaded",
                    tool_count=len(mcp_tools),
                    server_count=len(agent_config.mcp_servers),
                )
        except Exception:
            logger.warning(
                "mcp tools init failed, starting without external tools",
                exc_info=True,
            )

        all_tools = ks_tools + [load_skill, create_artifact] + mcp_tools

        builder = build_graph(
            model=llm,
            tools=all_tools,
            agent_config=agent_config,
            skills_index=skills_idx,
            summarization_model=summarization_llm,
        )
        graph = compile_graph(builder, checkpointer=checkpointer, store=store)
        app.state.agent_runner = LangGraphAgentRunner(graph)

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

    # Health check (no /api prefix — used by Docker health check)
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

    # Serve frontend static files (only when dist exists — Docker mode)
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dir.exists():
        frontend_resolved = frontend_dir.resolve()

        # JS, CSS, images from Vite build
        app.mount(
            "/assets",
            StaticFiles(directory=str(frontend_resolved / "assets")),
            name="assets",
        )

        # SPA fallback: unknown paths → index.html
        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str) -> FileResponse:
            # Guard: unknown /api paths → 404 JSON, not index.html
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")

            # Path traversal protection
            file_path = (frontend_resolved / full_path).resolve()
            if file_path.is_file() and file_path.is_relative_to(frontend_resolved):
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_resolved / "index.html"))

    return app


app = create_app()
