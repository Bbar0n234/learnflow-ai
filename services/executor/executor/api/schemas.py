"""Request/response schemas for `POST /jobs`."""

from typing import Self

from pydantic import BaseModel, model_validator


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
    timeout: float | None = None

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
