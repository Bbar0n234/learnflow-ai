"""Internal exceptions of the sandbox subsystem.

Narrow, subsystem-local exceptions (conventions.md § Модель ошибок, case 2):
they carry no HTTP semantics of their own — `AppError` would force a
fictitious `status` onto a layer that has no business knowing about
transport. Gated at the HTTP barrier in `executor.api.routes` (T3.5) into
4xx responses, never reach the client as raw exceptions.
"""

from pathlib import Path


class InvalidProjectIdError(Exception):
    """`project_id` is not a single safe path segment.

    Covers both the syntactic check (`^[A-Za-z0-9._-]{1,128}$`, not
    `.`/`..`) and the defense-in-depth resolved-path check
    (`is_relative_to(workspaces_root)`).
    """

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"invalid project_id: {project_id!r}")


class WorkspaceMissingError(Exception):
    """Resolved workspace directory does not exist on disk.

    The executor never creates workspace directories itself (design-brief
    § Executor: mkdir is a backend responsibility) — an absent workspace is
    a request error, not something to paper over.
    """

    def __init__(self, project_id: str, path: Path) -> None:
        self.project_id = project_id
        self.path = path
        super().__init__(f"workspace missing for project_id={project_id!r}: {path}")
