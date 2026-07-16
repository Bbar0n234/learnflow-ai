import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langfuse import get_client as get_langfuse_client
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import (
    PromptsRegistry,
    load_agent_config,
    load_error_messages,
    load_pricing_config,
    load_prompt_fragments,
    load_prompts_registry,
)
from app.agent.graph_factory import GraphFactory
from app.agent.runner import LangGraphAgentRunner
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.classifier import LLMClassifier
from app.agent.security.config import checkpoint_configs, load_security_config
from app.agent.security.corpus import (
    collect_fragment_corpus,
    collect_tool_registry,
)
from app.agent.security.detectors import (
    CanaryDetector,
    FragmentDetector,
    PairedToolIdentifierDetector,
    UnicodeDetector,
)
from app.agent.security.detectors.base import DeterministicDetector
from app.agent.security.guard import SecurityGuard
from app.agent.security.observer import GuardObserver
from app.agent.security.types import Checkpoint, Verdict
from app.agent.stream_events import StreamEventMapper
from app.agent.tools import (
    ks_tools,
    make_create_artifact_tool,
    make_generate_image_tool,
    make_load_skill_tool,
    scan_skills_index,
    user_memory_tools,
)
from app.agent.tracing import AgentRunTracer
from app.api.problem import TYPE_PREFIX, problem_response, register_problem_handlers
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
    ensure_security_score_config,
    init_langfuse,
    shutdown_langfuse,
)
from app.infra.langgraph import create_checkpointer, create_store
from app.infra.llm import create_guard_llm
from app.infra.logging import setup_logging
from app.infra.mcp import create_mcp_client
from app.infra.prompt_provider import PromptProvider
from app.infra.rate_limit import RateLimiter
from app.infra.redis import create_redis
from app.security_pipeline.processor import make_security_event_processor
from app.security_pipeline.transport import (
    EventTransportHolder,
    RedisEventTransport,
)
from app.services.encryption import EncryptionService
from app.services.mcp_server import (
    fetch_remote_metadata,
    serialize_mcp_meta_blob,
)
from app.services.mcp_tool_resolver import MCPToolResolver
from app.services.model_config_resolver import ModelConfigResolver

logger = structlog.get_logger()


def _content_hash(text: str, config: dict[str, Any]) -> str:
    return hashlib.sha256(
        (text + json.dumps(config, sort_keys=True)).encode()
    ).hexdigest()


async def _validate_builtin_mcp(
    servers: dict[str, Any],
    guard: Any,
    timeout: int,
) -> set[str]:
    """Validate each enabled remote built-in MCP server at startup.

    Fetches remote ``tools/list`` and runs the guard against the full
    metadata blob. Returns names of servers to disable (fetch failed OR
    guard fired INJECTION). ``stdio`` / disabled servers are skipped.
    """
    disabled: set[str] = set()
    for name, cfg in servers.items():
        if not cfg.enabled or cfg.transport == "stdio":
            continue
        api_key = os.environ.get(cfg.api_key_env, "") if cfg.api_key_env else None
        try:
            remote_tools = await fetch_remote_metadata(
                cfg.url or "", cfg.transport, api_key, timeout
            )
            blob = serialize_mcp_meta_blob(
                name=name,
                transport=cfg.transport,
                url=cfg.url or "",
                allowed_tools=cfg.allowed_tools or [],
                remote_tools=remote_tools,
            )
            result = await guard.check(
                blob,
                Checkpoint.MCP_METADATA,
                trace_ctx={"top_level": True, "scope": "mcp.builtin"},
            )
            if result.verdict == Verdict.INJECTION:
                logger.warning(
                    "built-in mcp disabled after guard failure",
                    name=name,
                    detection_layer=(
                        result.detection_layer.value if result.detection_layer else None
                    ),
                )
                disabled.add(name)
        except Exception:
            logger.warning(
                "built-in mcp disabled after guard/fetch failure",
                name=name,
                exc_info=True,
            )
            disabled.add(name)
    return disabled


def _seed_prompts(
    langfuse: Any,
    prompts_dir: Path,
    agent_config: Any,
    security_config: Any,
    prompts_registry: PromptsRegistry,
    label: str,
) -> None:
    """Seed prompts to Langfuse on startup (idempotent, duplicate-safe).

    Prompt names are qualified with label: "system--development", "system--production".
    This gives full isolation between environments — each has its own version history.
    Dedup compares file content against all versions of the qualified prompt.
    """
    for prompt_name in prompts_registry.prompts:
        file_path = prompts_dir / f"{prompt_name}.txt"
        if not file_path.exists():
            continue

        qualified = f"{prompt_name}--{label}"
        file_text = file_path.read_text(encoding="utf-8")
        file_config = prompts_registry.resolve(
            prompt_name, agent_config, security_config
        )
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
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter()

    # Holder is created up front so the structlog processor has something to
    # bind to, then populated when Redis is available below.
    transport_holder = EventTransportHolder()
    app.state.security_transport_holder = transport_holder

    setup_logging(
        log_level=settings.log_level,
        config_path=Path(__file__).resolve().parents[2] / "configs" / "logging.yaml",
        security_event_processor=make_security_event_processor(transport_holder),
        log_file=settings.log_file,
    )

    langfuse_enabled = False
    try:
        langfuse_enabled = init_langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
        )
    except Exception:
        logger.warning(
            "langfuse init failed, proceeding without tracing", exc_info=True
        )

    agent_config = load_agent_config()
    security_config = load_security_config()
    pricing_config = load_pricing_config()
    error_messages = load_error_messages()
    prompt_fragments = load_prompt_fragments()
    prompts_registry = load_prompts_registry()

    try:
        ensure_model_definitions(pricing_config.models, enabled=langfuse_enabled)
    except Exception:
        logger.warning("langfuse model definitions init failed", exc_info=True)

    try:
        ensure_security_score_config(enabled=langfuse_enabled)
    except Exception:
        logger.warning("langfuse security score config init failed", exc_info=True)

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

    if app.state.redis is not None:
        event_transport = RedisEventTransport(
            redis_client=app.state.redis,
            queue_maxsize=1000,
        )
        transport_holder.set(event_transport)
        publisher_task = asyncio.create_task(event_transport.publisher_loop())
        app.state.security_publisher_task = publisher_task
        logger.info("security event publisher started")

    # PromptProvider
    prompts_dir = Path(__file__).resolve().parents[2] / "configs" / "prompts"
    langfuse_client = None
    if langfuse_enabled:
        langfuse_client = get_langfuse_client()

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
            langfuse_client,
            prompts_dir,
            agent_config,
            security_config,
            prompts_registry,
            settings.langfuse_prompt_label,
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
        generate_image = make_generate_image_tool(
            app.state.session_factory,
            settings,
            agent_config.image,
            langfuse_enabled=langfuse_enabled,
        )

        internal_tools: list = (
            ks_tools + user_memory_tools + [load_skill, create_artifact, generate_image]
        )

        # Security guard (Sec 2.0 — always on). Must exist before MCP built-in
        # validation so the startup guard can call it.
        guard_llm = create_guard_llm(settings, security_config)
        fragment_corpus = collect_fragment_corpus(
            system_prompt=prompt_provider.load_file("system"),
            guard_classifier_prompt=prompt_provider.load_file("security-classifier"),
            internal_tools=internal_tools,
        )
        tool_registry = collect_tool_registry(internal_tools)

        detectors: list[DeterministicDetector] = [
            CanaryDetector(),
            UnicodeDetector(),
            PairedToolIdentifierDetector(
                tool_registry,
                min_compromised_tools=security_config.detectors.paired.min_compromised_tools,
                min_params_per_tool=security_config.detectors.paired.min_params_per_tool,
            ),
            FragmentDetector(
                fragment_corpus,
                window_size=security_config.detectors.fragment.window_size,
                stride=security_config.detectors.fragment.stride,
                min_unique_matches=security_config.detectors.fragment.min_unique_matches,
            ),
        ]
        classifier = LLMClassifier(
            llm=guard_llm,
            prompt_provider=prompt_provider,
            security_config=security_config,
            checkpoint_configs=checkpoint_configs(security_config),
        )
        security_guard = SecurityGuard(
            detectors=detectors,
            classifier=classifier,
            observer=GuardObserver(enabled=langfuse_enabled),
            config=security_config,
        )
        logger.info(
            "security guard initialized",
            guard_model=security_config.llm_classifier.model,
            corpus_items=len(fragment_corpus),
            tool_registry_size=len(tool_registry),
        )

        # Built-in MCP validation: fetch remote tools/list + run guard. A
        # server that fails the fetch or the guard check is excluded from the
        # runtime tool registry. App still boots (graceful disable).
        disabled_builtin_mcp: set[str] = await _validate_builtin_mcp(
            agent_config.mcp_servers, security_guard, settings.mcp_timeout_seconds
        )
        app.state.disabled_builtin_mcp = disabled_builtin_mcp

        # MCP external tools (graceful degradation)
        mcp_tools: list = []
        try:
            active_mcp: dict[str, Any] = {
                name: cfg
                for name, cfg in agent_config.mcp_servers.items()
                if cfg.enabled and name not in disabled_builtin_mcp
            }
            mcp_client = create_mcp_client(
                active_mcp, timeout=settings.mcp_timeout_seconds
            )
            if mcp_client is not None:
                for server_name, server_config in active_mcp.items():
                    tools = await mcp_client.get_tools(server_name=server_name)
                    if server_config.allowed_tools:
                        allowed = set(server_config.allowed_tools)
                        tools = [t for t in tools if t.name in allowed]
                    mcp_tools.extend(tools)
                logger.info(
                    "mcp tools loaded",
                    tool_count=len(mcp_tools),
                    servers_active=len(active_mcp),
                    servers_total=len(agent_config.mcp_servers),
                    servers_disabled=len(disabled_builtin_mcp),
                )
        except Exception:
            logger.warning(
                "mcp tools init failed, starting without external tools",
                exc_info=True,
            )

        global_tools = (
            ks_tools
            + user_memory_tools
            + [load_skill, create_artifact, generate_image]
            + mcp_tools
        )

        # GraphFactory + ModelConfigResolver
        graph_factory = GraphFactory(
            settings=settings,
            agent_config=agent_config,
            prompt_fragments=prompt_fragments,
            security_messages=security_config.messages,
            global_tools=global_tools,
            skills_index=skills_idx,
            checkpointer=checkpointer,
            store=store,
            prompt_provider=prompt_provider,
            security_guard=security_guard,
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
            mcp_timeout=settings.mcp_timeout_seconds,
        )

        app.state.tool_resolver = tool_resolver

        if not settings.canary_secret:
            logger.warning("CANARY_SECRET not configured, canary protection disabled")

        checkpoint_history = CheckpointHistory(checkpointer, security_config.messages)
        runtime_security = RuntimeSecurityEnforcer(
            guard=security_guard,
            security_messages=security_config.messages,
            history=checkpoint_history,
            session_factory=app.state.session_factory,
        )
        agent_tracer = AgentRunTracer(
            enabled=langfuse_enabled,
            security_messages=security_config.messages,
        )

        app.state.agent_runner = LangGraphAgentRunner(
            graph_factory=graph_factory,
            model_resolver=model_resolver,
            tracer=agent_tracer,
            enforcer=runtime_security,
            history=checkpoint_history,
            error_messages=error_messages,
            event_mapper=StreamEventMapper(),
            tool_resolver=tool_resolver,
            canary_secret=settings.canary_secret,
        )
        app.state.agent_config = agent_config
        app.state.security_config = security_config
        app.state.security_guard = security_guard
        app.state.pricing_config = pricing_config
        app.state.error_messages = error_messages
        app.state.prompt_fragments = prompt_fragments
        app.state.prompts_registry = prompts_registry

        yield

    # Graceful shutdown of security event publisher
    if hasattr(app.state, "security_publisher_task"):
        transport = app.state.security_transport_holder.get()
        if transport is not None:
            await transport.graceful_shutdown(timeout=5.0)
        app.state.security_publisher_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.security_publisher_task
        logger.info("security event publisher stopped")

    shutdown_langfuse()
    if app.state.redis:
        await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="LearnFlowAI", lifespan=lifespan)

    # Request ID + security context + Layer 3 generic-500 catch.
    #
    # Middleware ordering (Starlette): add_middleware inserts at the front of
    # the stack, so the LAST registered middleware is the OUTERMOST. CORS is
    # registered AFTER this one (below) and is therefore the outermost wrapper.
    # The generic-500 JSONResponse returned here flows back OUT through
    # CORSMiddleware and picks up Access-Control-Allow-Origin (F-API-01). A bare
    # add_exception_handler(Exception) would run in ServerErrorMiddleware,
    # OUTSIDE all user middleware including CORS, and the 500 would ship without
    # CORS headers — which is exactly why the catch lives here.
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        structlog.contextvars.clear_contextvars()
        request_id = str(uuid.uuid4())

        # Extract client IP (handle X-Forwarded-For for proxies)
        client_ip = "unknown"
        if request.client:
            client_ip = request.client.host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # Extract User-Agent and hash it
        user_agent = request.headers.get("User-Agent", "")
        user_agent_hash = hashlib.sha256(user_agent.encode()).hexdigest()

        # Bind security context
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            ip=client_ip,
            user_agent_hash=user_agent_hash,
        )
        try:
            response = await call_next(request)
            return response
        except Exception:
            logger.error("unhandled exception", exc_info=True)
            return problem_response(status=500, detail="Internal server error")

    # CORS — registered LAST so it is the OUTERMOST middleware and wraps the
    # generic-500 handler above; this is what lets 500 responses carry CORS
    # headers (F-API-01).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers — RFC 9457 problem+json
    register_problem_handlers(app)

    # Health check — honest 503 when DB is down (F-API-02).
    # response_model=None: the handler returns either a plain dict (200) or a
    # JSONResponse (503 problem+json); FastAPI cannot build a response model
    # from that union (Response subclass + dict) and would raise at startup.
    @app.get("/health", response_model=None)
    async def health(request: Request) -> JSONResponse | dict[str, str]:
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ok"}
        except OperationalError:
            logger.warning("health check: database unavailable", exc_info=True)
            return problem_response(
                status=503,
                detail="Database unavailable",
                type_=TYPE_PREFIX + "db-unavailable",
            )

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
