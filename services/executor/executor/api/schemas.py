"""Request/response schemas for `POST /jobs`."""

from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator


class JobRequest(BaseModel):
    """Job execution request.

    Exactly one of `code`/`cmd` must be set. Enforced by the schema, not an
    `if` in the handler (conventions/api.md § Status codes: validation is
    schema's job) — violating it surfaces as a plain `422` through FastAPI's
    default request-validation handling.
    """

    project_id: str
    code: str | None = None
    cmd: str | None = None
    # `gt=0`: a non-positive timeout is a caller bug, not a value the service
    # should quietly accept and clamp — clamping it would kill the job before
    # it starts and surface as an opaque "exceeded timeout of 0.0s" instead of
    # a `422` naming the actual mistake. The upper bound stays a runtime
    # clamp (`_clamp_timeout` in `executor.api.routes`), not a schema bound —
    # it is a defensive backstop keyed off `Settings.max_timeout_seconds`,
    # not a static invariant of the request shape.
    timeout: Annotated[float, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def _exactly_one_of_code_cmd(self) -> Self:
        if (self.code is None) == (self.cmd is None):
            raise ValueError("exactly one of `code` or `cmd` must be set")
        return self


class JobResponse(BaseModel):
    """Job execution result.

    Cross-track contract 2 (design-brief § Партиция треков) — these three
    fields are fixed and must not change without an explicit cross-track
    renegotiation.
    """

    stdout: str
    stderr: str
    exit_code: int
