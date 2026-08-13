"""Executor service main FastAPI application."""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from executor.api.deps import SettingsDep
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
    async def health_check(settings: SettingsDep) -> dict[str, str]:
        """Health check endpoint — open, no auth (compose polls it).

        Reports the sandbox state alongside liveness: a service running with
        `EXECUTOR_SANDBOX_ENABLED=false` is up but degraded to the point of
        having no isolation at all, and that has to be observable from
        outside the container, not only in its log stream.
        """
        return {
            "status": "ok",
            "sandbox": "enabled" if settings.sandbox_enabled else "disabled",
        }

    if not settings.sandbox_enabled:
        # ERROR, once, at startup: the per-job WARNING in `build_job_argv`
        # scrolls away in job noise, while this is the line an operator sees
        # when the service comes up. Not a hard startup failure — the project
        # carries no environment marker (`app_env`/`environment`) to tell a
        # dev host from production, and inventing one for this guard alone is
        # out of scope; the audit trail is this line plus `GET /health`.
        logger.error(
            "executor sandbox disabled — jobs run unisolated with rw access "
            "to every project workspace; never use outside a dev host",
            sandbox_enabled=False,
        )

    logger.info("executor service configured", log_level=settings.log_level)

    return app


app = create_app()
