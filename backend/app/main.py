import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from app.api.routes import artifacts, chats, messages, projects, sphere
from app.config import Settings
from app.infra.db import create_engine, create_session_factory
from app.infra.langgraph import create_checkpointer, create_store
from app.infra.llm import create_llm
from app.infra.mcp import create_mcp_client
from app.services.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    agent_config = load_agent_config()

    engine = create_engine(settings)
    # Fail-fast: verify DB is reachable at startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

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

        skills_dir = Path(__file__).resolve().parents[2] / "skills"
        load_skill = make_load_skill_tool(skills_dir)
        skills_idx = scan_skills_index(skills_dir)
        create_artifact = make_create_artifact_tool(app.state.session_factory)

        # MCP external tools (graceful degradation)
        mcp_tools: list = []
        try:
            mcp_client = create_mcp_client(agent_config.mcp_servers)
            if mcp_client is not None:
                mcp_tools = await mcp_client.get_tools()
                logger.info(
                    "Loaded %d MCP tools from %d server(s)",
                    len(mcp_tools),
                    len(agent_config.mcp_servers),
                )
        except Exception:
            logger.warning(
                "Failed to initialize MCP tools, starting without external tools",
                exc_info=True,
            )

        all_tools = ks_tools + [load_skill, create_artifact] + mcp_tools

        builder = build_graph(
            model=llm,
            tools=all_tools,
            agent_config=agent_config,
            skills_index=skills_idx,
        )
        graph = compile_graph(builder, checkpointer=checkpointer, store=store)
        app.state.agent_runner = LangGraphAgentRunner(graph)

        yield

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

    # Exception handlers
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: object, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # Routes
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects.router)
    app.include_router(chats.router)
    app.include_router(messages.router)
    app.include_router(artifacts.router)
    app.include_router(sphere.router)

    return app


app = create_app()
