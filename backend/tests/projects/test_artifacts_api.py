"""Artifacts REST on the file-backed model — integration through the ASGI client.

Route -> ``ArtifactWorkspaceService`` -> real files on a throwaway workspace
root, with ownership resolved against real Postgres. The contract that moved in
this iteration is addressing: an artifact is identified by its path below
``artifacts/``, carried in a ``path`` query parameter rather than a URL segment
(a segment cannot hold the slashes a nested artifact needs), and the same
route answers list (no ``path``) and detail (``path`` present).

The suite pins the three answers a caller can get for a path — a file (200), a
valid path with nothing behind it (404), and a path that escapes the workspace
(422 problem+json, the adversarial case) — plus the caching contract ``media``
now needs: the identity is rewritable, so the response must revalidate
(``ETag``/``no-cache``) instead of being cached forever the way the old
UUID-addressed immutable blob was.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import unquote

import pytest
from app.models.user import User
from app.storage.workspace import Workspace
from fastapi import FastAPI
from httpx import AsyncClient

from tests.projects._builders import create_other_project, create_owned_project

pytestmark = pytest.mark.integration


def _artifact(root: Path, project_id: uuid.UUID, relative: str, content: str) -> Path:
    path = root / str(project_id) / "artifacts" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _binary_artifact(
    root: Path, project_id: uuid.UUID, relative: str, data: bytes
) -> Path:
    path = root / str(project_id) / "artifacts" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# --- list -------------------------------------------------------------------


async def test_list_artifacts_of_an_untouched_project_is_empty(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    # Workspace creation is lazy: a project nobody wrote to has no directory
    # at all, and that must read as "no artifacts", not as an error.
    project = await create_owned_project(current_user)

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_list_artifacts_returns_nested_paths_newest_first(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    older = _artifact(workspaces_root, project.id, "notes.md", "# Notes")
    newer = _artifact(workspaces_root, project.id, "lecture-1/slides.md", "# Slides")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    body = response.json()
    assert body["total"] == 2
    assert [item["path"] for item in body["items"]] == [
        "lecture-1/slides.md",
        "notes.md",
    ]
    assert body["items"][0]["title"] == "slides.md"
    assert body["items"][0]["type"] == "md"


async def test_list_artifacts_honours_limit_and_offset(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    for index in range(3):
        path = _artifact(workspaces_root, project.id, f"a{index}.md", "x")
        os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"limit": 1, "offset": 1}
    )

    body = response.json()
    assert [item["path"] for item in body["items"]] == ["a1.md"]
    assert (body["total"], body["limit"], body["offset"]) == (3, 1, 1)


async def test_list_artifacts_keeps_answering_when_a_job_left_a_symlink(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
    tmp_path: Path,
) -> None:
    """A single symlink in `artifacts/` used to take the whole panel down.

    A job can create one (`ln -s /etc/passwd artifacts/leak.txt`) deliberately
    or as a toolchain side effect, and the agent has no tool to remove it: the
    422/500 it caused would have stayed until someone touched the volume by
    hand. The listing skips it now — the panel answers 200 with the project's
    real files, and the link is not among them under any name.
    """
    project = await create_owned_project(current_user)
    outside = tmp_path / "outside.txt"
    outside.write_text("s3cret", encoding="utf-8")
    _artifact(workspaces_root, project.id, "notes.md", "# Notes")
    artifacts_dir = workspaces_root / str(project.id) / "artifacts"
    (artifacts_dir / "leak.txt").symlink_to(outside)
    (artifacts_dir / "dangling.txt").symlink_to(artifacts_dir / "nope.txt")

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 200
    body = response.json()
    assert [item["path"] for item in body["items"]] == ["notes.md"]
    assert body["total"] == 1


async def test_list_artifacts_of_someone_elses_project_is_404(
    client: AsyncClient, workspace: Workspace
) -> None:
    project = await create_other_project()

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param("", id="detail"),
        pytest.param("/media", id="media"),
        pytest.param("/download", id="download"),
    ],
)
async def test_reading_an_artifact_of_someone_elses_project_is_404(
    client: AsyncClient,
    workspace: Workspace,
    workspaces_root: Path,
    endpoint: str,
) -> None:
    # Ownership is the outer gate on every one of the four routes, and it has
    # to hold on the reading three as well as on list: the path parameter is
    # attacker-chosen, so a route that forgot the dependency would happily
    # serve a file that exists in a stranger's workspace. The file is real
    # here on purpose — a 404 from "nothing to read" would prove nothing.
    project = await create_other_project()
    _artifact(workspaces_root, project.id, "notes.md", "их конспект")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts{endpoint}", params={"path": "notes.md"}
    )

    assert response.status_code == 404
    assert "их конспект".encode() not in response.content


# --- detail -----------------------------------------------------------------


async def test_get_artifact_returns_metadata_and_text_content(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "lecture-1/slides.md", "# Slides")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts",
        params={"path": "lecture-1/slides.md"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "lecture-1/slides.md"
    assert body["title"] == "slides.md"
    assert body["type"] == "md"
    assert body["content"] == "# Slides"
    assert "updated_at" in body


async def test_get_a_binary_artifact_omits_the_content_field(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # Bytes travel through `media`, never inline in JSON — the field is absent
    # rather than null, which is what the frontend DTO expects.
    project = await create_owned_project(current_user)
    _binary_artifact(workspaces_root, project.id, "chart.png", b"\x89PNG\r\n\x1a\n\xff")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"path": "chart.png"}
    )

    assert response.status_code == 200
    assert "content" not in response.json()


async def test_get_an_artifact_whose_path_is_not_ascii(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # Cyrillic filenames are produced routinely — `generate_image` slugs a
    # Russian title, uploads keep the name the user picked — so the path that
    # identifies an artifact is regularly non-ASCII. It has to survive the
    # round trip through `?path=` percent-encoding and come back as the same
    # string, byte for byte, in `path` and `title`.
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "лекции/Лекция №1.md", "# Лекция")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts",
        params={"path": "лекции/Лекция №1.md"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "лекции/Лекция №1.md"
    assert body["title"] == "Лекция №1.md"
    assert body["content"] == "# Лекция"


async def test_get_a_huge_artifact_is_capped_by_the_same_read_ceiling(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
    app: FastAPI,
    tmp_path: Path,
) -> None:
    """Detail is a second read path over the raw file — it needs the same knob.

    The agent's `read_file` is bounded by `Workspace.read_text`; this endpoint
    reaches the file directly, so it used to serve whatever a job had written
    there in full. A gigabyte of `cat` output in `artifacts/` is exactly the
    failure the executor's own output ceiling exists to prevent, reintroduced
    through REST. The ceiling is dialled down here rather than the file dialled
    up — the number is an operational knob, its enforcement is the contract.
    """
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "huge.md", "a" * 5_000)
    app.state.workspace = Workspace(
        workspaces_root=workspaces_root,
        skills_root=tmp_path / "skills",
        read_limit_chars=64,
        diff_file_limit_bytes=1_000_000,
        diff_total_limit_bytes=10_000_000,
    )

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"path": "huge.md"}
    )

    assert response.status_code == 200
    assert response.json()["content"] == "a" * 64


async def test_get_a_missing_artifact_is_404(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"path": "gone.md"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("../../etc/passwd", id="traversal"),
        pytest.param("../../../../../../etc/shadow", id="deep-traversal"),
    ],
)
async def test_get_an_artifact_outside_the_workspace_is_422_problem(
    client: AsyncClient, current_user: User, workspace: Workspace, path: str
) -> None:
    # A path escape is a malformed/adversarial request, not a missing file —
    # 422 keeps it distinguishable from the ordinary "not there" 404.
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"path": path}
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:learnflow:invalid-path"


async def test_get_an_absolute_path_reads_nothing_off_the_host(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    # The zone prefix is prepended to the parameter, so an absolute path
    # degrades into a relative one inside `artifacts/` — nothing off the host
    # is reachable, and the answer is the ordinary "no such artifact".
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts", params={"path": "/etc/passwd"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param("", id="detail"),
        pytest.param("/media", id="media"),
        pytest.param("/download", id="download"),
    ],
)
async def test_artifacts_endpoints_do_not_serve_files_outside_the_artifacts_zone(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
    endpoint: str,
) -> None:
    project = await create_owned_project(current_user)
    upload = workspaces_root / str(project.id) / "uploads"
    upload.mkdir(parents=True)
    (upload / "lecture.txt").write_text("private upload", encoding="utf-8")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts{endpoint}",
        params={"path": "../uploads/lecture.txt"},
    )

    assert response.status_code in (404, 422)
    assert b"private upload" not in response.content


# --- media ------------------------------------------------------------------


async def test_media_returns_bytes_with_revalidating_cache_headers(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    _binary_artifact(workspaces_root, project.id, "chart.png", b"\x89PNG-data")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/media", params={"path": "chart.png"}
    )

    assert response.status_code == 200
    assert response.content == b"\x89PNG-data"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"]
    assert response.headers["last-modified"]


async def test_media_answers_304_when_the_client_etag_still_matches(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    _binary_artifact(workspaces_root, project.id, "chart.png", b"\x89PNG-data")
    url = f"/api/projects/{project.id}/artifacts/media"
    first = await client.get(url, params={"path": "chart.png"})

    second = await client.get(
        url,
        params={"path": "chart.png"},
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert second.status_code == 304
    assert second.content == b""


async def test_media_answers_200_after_the_file_was_rewritten(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # The path is a rewritable identity — this is the whole reason the cache
    # revalidates instead of being immutable.
    project = await create_owned_project(current_user)
    target = _binary_artifact(workspaces_root, project.id, "chart.png", b"old")
    url = f"/api/projects/{project.id}/artifacts/media"
    first = await client.get(url, params={"path": "chart.png"})
    target.write_bytes(b"new-and-longer")

    second = await client.get(
        url,
        params={"path": "chart.png"},
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert second.status_code == 200
    assert second.content == b"new-and-longer"


async def test_media_of_a_missing_artifact_is_404(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/media", params={"path": "gone.png"}
    )

    assert response.status_code == 404


# --- download ---------------------------------------------------------------


async def test_download_returns_the_file_as_an_attachment(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "lecture-1/slides.md", "# Slides")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/download",
        params={"path": "lecture-1/slides.md"},
    )

    assert response.status_code == 200
    assert response.content == b"# Slides"
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "slides.md" in response.headers["content-disposition"]


async def test_download_encodes_a_non_ascii_filename_in_the_disposition(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # `Content-Disposition` is a latin-1 header, so a Cyrillic filename can
    # only travel as RFC 5987 `filename*=UTF-8''<percent-encoded>`; the plain
    # `filename=` form would either mangle the name or make the response
    # unencodable. This is the one place a non-ASCII artifact path breaks
    # visibly, and the browser's Save-as name comes straight out of it.
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "лекции/Лекция №1.md", "# Лекция")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/download",
        params={"path": "лекции/Лекция №1.md"},
    )

    assert response.status_code == 200
    assert response.content == "# Лекция".encode()
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename*=UTF-8''")
    assert unquote(disposition.split("''", 1)[1]) == "Лекция №1.md"


async def test_download_of_a_missing_artifact_is_404(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/download", params={"path": "gone.md"}
    )

    assert response.status_code == 404


async def test_download_no_longer_offers_pdf_conversion(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # The wkhtmltopdf path was dropped with the PG model (PDF export becomes a
    # skill over the runtime): `format` is not a parameter any more, and an
    # unknown query parameter must not change what comes back.
    project = await create_owned_project(current_user)
    _artifact(workspaces_root, project.id, "notes.md", "# Notes")

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/download",
        params={"path": "notes.md", "format": "pdf"},
    )

    assert response.status_code == 200
    assert response.content == b"# Notes"
    assert not response.headers["content-type"].startswith("application/pdf")
