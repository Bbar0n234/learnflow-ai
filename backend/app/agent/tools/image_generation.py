"""Agent-facing image-generation tool (ADR-032, T1.7 file-write migration).

`generate_image` calls the configured image model, then writes the result
directly into `artifacts/` through the workspace file layer instead of the
former PG artifact-row + blob transaction: the file *is* the artifact now
(design-brief § Артефакты) — the same "path = identity" contract
`write_file`/execution jobs already produce. An empty/unusable title and a
repeated one are handled the same way `write_file`/uploads accept a name
(`sanitize_filename`/`unique_path`, `app/storage/workspace.py`): a collision
never overwrites what an earlier chat turn's history entry still points at.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from langchain_core.tools import BaseTool, tool
from langfuse import get_client
from langgraph.prebuilt import ToolRuntime

from app.agent.config import ImageConfig
from app.config import Settings
from app.infra.image_generation import generate_image as call_generate_image
from app.storage.workspace import (
    ARTIFACTS_DIR,
    Workspace,
    artifact_type,
    extension_from_mime,
    sanitize_filename,
    unique_path,
)


def make_generate_image_tool(
    workspace: Workspace,
    settings: Settings,
    image_config: ImageConfig,
    *,
    langfuse_enabled: bool = False,
) -> BaseTool:
    """Create a generate_image tool bound to the given dependencies."""

    @tool(response_format="content_and_artifact")
    async def generate_image(
        prompt: str,
        title: str,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        *,
        runtime: ToolRuntime,
    ) -> tuple[str, list[dict[str, str]]]:
        """Generate an image with the configured image model and save it as a project artifact.

        Use this when the user asks for an illustration, cover image, diagram
        mockup, icon, or banner — anything that should be a real generated
        image, not described in text. The underlying model is a natively
        multimodal LLM without a separate prompt rewriter: your prompt goes
        to it as-is, so prompt quality is entirely on you.

        You will not see the resulting image — only a text confirmation
        (title, saved filename, resolution, cost). If the user wants
        changes, they will describe them in words ("darker", "remove the
        text"); revise the prompt and call this tool again.

        Prompt guidelines:
            Write a coherent paragraph of ~50-120 words, not a list of tags.
            Structure: subject -> action -> setting -> composition/camera ->
            style -> lighting.
            - Be concrete about details (materials, colors) and state the
              image's purpose ("cover for a technical article about ...") —
              the model uses that intent.
            - Use only positive phrasing: instead of "no people", write
              "empty street".
            - Describe composition like a photographer: wide-angle, macro,
              low-angle, golden hour, shallow depth of field.
            - On-image text: give the exact wording in double quotes and
              describe the font in words ("bold sans-serif"). Russian text is
              supported; keep wording short (1-4 words).

        Args:
            prompt: Full image description per the guidelines above.
            title: Short descriptive title for the artifact. Drives the
                saved filename (sanitized; a repeated title gets a numeric
                suffix, never overwriting an earlier image).
            aspect_ratio: Composition — "16:9" (article cover; some platforms
                crop previews to ~2:1, keep key elements centered), "4:3"
                (illustration), "1:1" (icon), "21:9"/"4:1" (banner). Omit to
                use the model's default.
            resolution: "1K" — default, in-text illustration; "512" — drafts
                and variants; "2K" — covers/hero images; "4K" — only on
                explicit user request. Each step up costs noticeably more —
                do not raise it without a reason.
        """
        if runtime.context is None:
            raise RuntimeError(
                "generate_image requires AgentContext but none was provided"
            )
        project_id = runtime.context.project_id

        result = await call_generate_image(
            settings,
            image_config,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        filename = await asyncio.to_thread(
            _save_image, workspace, project_id, title, result.data, result.media_type
        )

        if langfuse_enabled:
            with contextlib.suppress(Exception):
                gen_kwargs: dict[str, Any] = {
                    "as_type": "generation",
                    "name": "generate-image",
                    "model": image_config.model,
                    "input": prompt,
                    "output": {
                        "artifact_path": filename,
                        "media_type": result.media_type,
                    },
                }
                if result.cost is not None:
                    gen_kwargs["cost_details"] = {"total": result.cost}
                with get_client().start_as_current_observation(**gen_kwargs):
                    pass

        resolution_label = resolution or "provider default"
        cost_label = f"${result.cost:.4f}" if result.cost is not None else "unknown"
        text = (
            f"Image saved: '{title}' -> {filename} "
            f"(resolution={resolution_label}, cost={cost_label})"
        )
        return (
            text,
            # Single-element list, same reasoning as write_file's artifacts/
            # writes: `kind` is always "created" (this tool only ever picks a
            # fresh, collision-free name — it never overwrites). `path`/
            # `title` carry the saved filename, not the model-supplied
            # `title` arg verbatim — that string is only the slug's raw
            # material (design-brief § Артефакты: `type="image"` уходит, the
            # model title is not the wire title).
            [
                {
                    "path": filename,
                    "title": filename,
                    "type": artifact_type(filename),
                    "kind": "created",
                }
            ],
        )

    return generate_image


def _save_image(
    workspace: Workspace,
    project_id: str,
    title: str,
    data: bytes,
    media_type: str,
) -> str:
    """Pick a collision-free filename under `artifacts/` and write `data` there.

    Directory resolution, the collision check (`unique_path`) and the atomic
    write happen inside one sync call, run off the event loop by the caller
    (`asyncio.to_thread`) — kept together so the window between "name
    chosen" and "file written" is as small as possible.
    """
    extension = extension_from_mime(media_type)
    stem = sanitize_filename(title, fallback_stem="image")
    artifacts_dir = workspace.resolve_path(project_id, ARTIFACTS_DIR, write=True)
    target = unique_path(artifacts_dir, f"{stem}.{extension}")
    workspace.write_bytes(project_id, f"{ARTIFACTS_DIR}/{target.name}", data)
    return target.name
