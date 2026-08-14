"""Unit: `generate_image` after the move onto workspace files (T1.7).

The image call itself is unchanged and irrelevant here — it is faked at the
`app.infra.image_generation` seam (network, cost, non-determinism). What this
suite covers is the half that changed: where the bytes land and what the tool
reports back. The result is now a file under `artifacts/`, named from a slug
of the model-supplied title, and the envelope carries the *saved filename* on
both `path` and `title` — not the raw title argument, or the card in the chat
feed would disagree with the row in the artifacts list for the same file.

Naming is the risky part and gets the negatives: a repeated title must not
overwrite the image an earlier turn's history still points at, and a title
made of nothing usable must still produce a name that reads as an image.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from app.agent.config import ImageConfig
from app.agent.tools import image_generation as image_module
from app.agent.tools.image_generation import make_generate_image_tool
from app.config import Settings
from app.infra.image_generation import ImageGenerationResult
from app.storage.workspace import TMP_FILE_PREFIX, Workspace
from langchain_core.tools import BaseTool, StructuredTool
from learnflow_testing.workspace import (
    PROJECT_ID,
    runtime,
    runtime_without_context,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def workspace(workspaces_root: Path, tmp_path: Path) -> Workspace:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    return Workspace(
        workspaces_root=workspaces_root,
        skills_root=skills_root,
        read_limit_chars=50_000,
        diff_file_limit_bytes=1_000_000,
        diff_total_limit_bytes=10_000_000,
    )


@pytest.fixture
def artifacts_dir(workspaces_root: Path) -> Path:
    return workspaces_root / PROJECT_ID / "artifacts"


def _tool(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    *,
    data: bytes = b"\x89PNG-bytes",
    media_type: str = "image/png",
) -> BaseTool:
    """The tool with the image API replaced by a programmed result."""

    async def fake_call(*_args: Any, **_kwargs: Any) -> ImageGenerationResult:
        return ImageGenerationResult(data=data, media_type=media_type, cost=0.01)

    monkeypatch.setattr(image_module, "call_generate_image", fake_call)
    return make_generate_image_tool(
        workspace, Settings(), ImageConfig(model="fake-image-model")
    )


async def _call(tool: BaseTool, **kwargs: Any) -> Any:
    coroutine = cast("StructuredTool", tool).coroutine
    assert coroutine is not None
    return await coroutine(**kwargs)


async def test_generate_image_saves_the_bytes_as_an_artifact_file(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool(workspace, monkeypatch)

    text, artifacts = await _call(
        tool, prompt="a neon city", title="Neon City", runtime=runtime()
    )

    assert (artifacts_dir / "Neon City.png").read_bytes() == b"\x89PNG-bytes"
    assert artifacts == [
        {
            "path": "Neon City.png",
            "title": "Neon City.png",
            "type": "png",
            "kind": "created",
        }
    ]
    assert "Neon City.png" in text


async def test_generate_image_takes_the_extension_from_the_response_mime(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool(workspace, monkeypatch, data=b"webp", media_type="image/webp")

    _, artifacts = await _call(tool, prompt="p", title="Cover", runtime=runtime())

    assert artifacts[0]["path"] == "Cover.webp"
    assert (artifacts_dir / "Cover.webp").exists()


async def test_generate_image_with_a_repeated_title_does_not_overwrite(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The earlier image is what an older chat message's card still points at.
    tool = _tool(workspace, monkeypatch, data=b"first")
    await _call(tool, prompt="p", title="Cover", runtime=runtime())
    tool = _tool(workspace, monkeypatch, data=b"second")

    _, artifacts = await _call(tool, prompt="p", title="Cover", runtime=runtime())

    assert artifacts[0]["path"] == "Cover-1.png"
    assert (artifacts_dir / "Cover.png").read_bytes() == b"first"
    assert (artifacts_dir / "Cover-1.png").read_bytes() == b"second"


async def test_generate_image_falls_back_to_an_image_name_for_an_unusable_title(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool(workspace, monkeypatch)

    _, artifacts = await _call(tool, prompt="p", title="\x00\x01", runtime=runtime())

    assert artifacts[0]["path"].startswith("image-")
    assert artifacts[0]["path"].endswith(".png")
    assert (artifacts_dir / artifacts[0]["path"]).exists()


async def test_generate_image_keeps_a_cyrillic_title_in_the_filename(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Path *is* identity here and the REST layer carries Unicode fine — the
    # slug only strips what a filesystem cannot take.
    tool = _tool(workspace, monkeypatch)

    _, artifacts = await _call(
        tool, prompt="p", title="Обложка лекции", runtime=runtime()
    )

    assert artifacts[0]["path"] == "Обложка лекции.png"


async def test_generate_image_leaves_no_temp_file_behind(
    workspace: Workspace, artifacts_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool(workspace, monkeypatch)

    await _call(tool, prompt="p", title="Cover", runtime=runtime())

    assert [
        p.name for p in artifacts_dir.iterdir() if p.name.startswith(TMP_FILE_PREFIX)
    ] == []


async def test_generate_image_without_an_agent_context_raises(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `project_id` decides whose workspace the file lands in — no context
    # means no safe default, so the tool must refuse rather than guess.
    tool = _tool(workspace, monkeypatch)

    with pytest.raises(RuntimeError):
        await _call(tool, prompt="p", title="Cover", runtime=runtime_without_context())
