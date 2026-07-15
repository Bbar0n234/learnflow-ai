from __future__ import annotations

import contextlib
import uuid
from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.config import ImageConfig
from app.config import Settings
from app.infra.image_generation import generate_image as call_generate_image
from app.repositories.artifact import ArtifactRepository
from app.repositories.blob_storage import PgBlobStorage


def make_generate_image_tool(
    session_factory: async_sessionmaker[AsyncSession],
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
    ) -> tuple[str, dict[str, str]]:
        """Generate an image with the configured image model and save it as a project artifact.

        Use this when the user asks for an illustration, cover image, diagram
        mockup, icon, or banner — anything that should be a real generated
        image, not described in text. The underlying model is a natively
        multimodal LLM without a separate prompt rewriter: your prompt goes
        to it as-is, so prompt quality is entirely on you.

        You will not see the resulting image — only a text confirmation
        (title, id, resolution, cost). If the user wants changes, they will
        describe them in words ("darker", "remove the text"); revise the
        prompt and call this tool again.

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
            title: Short descriptive title for the artifact.
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
        project_id = uuid.UUID(runtime.context.project_id)
        thread_id = uuid.UUID(runtime.config["configurable"]["thread_id"])

        result = await call_generate_image(
            settings,
            image_config,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        async with session_factory() as session, session.begin():
            artifact = await ArtifactRepository(session).create(
                project_id=project_id,
                title=title,
                type="image",
                content=prompt,
                thread_id=thread_id,
            )
            artifact_id = artifact.id
            await PgBlobStorage(session).put(
                artifact_id=artifact_id,
                data=result.data,
                mime_type=result.media_type,
            )

        if langfuse_enabled:
            with contextlib.suppress(Exception):
                # lazy: langfuse is optional; observation degrades gracefully
                from langfuse import get_client  # noqa: PLC0415

                gen_kwargs: dict[str, Any] = {
                    "as_type": "generation",
                    "name": "generate-image",
                    "model": image_config.model,
                    "input": prompt,
                    "output": {
                        "artifact_id": str(artifact_id),
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
            f"Image saved: '{title}' (id={artifact_id}, "
            f"resolution={resolution_label}, cost={cost_label})"
        )
        return (
            text,
            {"id": str(artifact_id), "title": title, "type": "image"},
        )

    return generate_image
