"""Executor service main FastAPI application."""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from executor.api.routes import router
from executor.config import Settings
from executor.exceptions import InvalidProjectIdError, WorkspaceMissingError
from executor.logging import configure_logging

logger = structlog.get_logger()


# Barrier exception handlers — `InvalidProjectIdError`/`WorkspaceMissingError`
# are internal exceptions of the sandbox subsystem (conventions.md § Модель
# ошибок, case 2: narrow, no HTTP semantics of their own), gated here into
# 4xx responses rather than raised as `HTTPException` from the domain layer.
# No RFC 9457 problem+json mirror for executor (design plan OQ-3, closed):
# a single internal machine client makes FastAPI's default response shape
# sufficient.
async def _invalid_project_id_handler(
    request: Request, exc: InvalidProjectIdError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _workspace_missing_handler(
    request: Request, exc: WorkspaceMissingError
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def create_app() -> FastAPI:
    settings = Settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Executor Service", version="0.1.0")
    app.state.settings = settings

    # `add_exception_handler`'s stub is invariant in the exception type it
    # accepts vs. the narrower type our handlers declare — same shape as the
    # existing `# type: ignore[arg-type]` precedent in
    # `siem_service/api/problem.py::register_problem_handlers`.
    app.add_exception_handler(InvalidProjectIdError, _invalid_project_id_handler)  # type: ignore[arg-type]
    app.add_exception_handler(WorkspaceMissingError, _workspace_missing_handler)  # type: ignore[arg-type]

    app.include_router(router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    logger.info("executor service configured", log_level=settings.log_level)

    return app


app = create_app()
