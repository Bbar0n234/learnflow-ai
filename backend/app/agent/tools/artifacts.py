from __future__ import annotations

import uuid

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.artifact import ArtifactRepository


def make_create_artifact_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> BaseTool:
    """Create a create_artifact tool bound to the given session factory."""

    @tool(response_format="content_and_artifact")
    async def create_artifact(
        title: str,
        content: str,
        type: str,
        runtime: ToolRuntime,
    ) -> tuple[str, dict[str, str]]:
        """Save agent's work result as a project artifact.

        Use this tool when you produce a structured deliverable for the user:
        study plans, summaries, outlines, code, etc.

        Args:
            title: Short descriptive title for the artifact.
            content: Full text content of the artifact.
            type: Artifact type (e.g. "plan", "summary", "outline", "code").
        """
        if runtime.context is None:
            raise RuntimeError(
                "create_artifact requires AgentContext but none was provided"
            )
        project_id = uuid.UUID(runtime.context.project_id)
        thread_id = uuid.UUID(runtime.config["configurable"]["thread_id"])

        async with session_factory() as session, session.begin():
            repo = ArtifactRepository(session)
            artifact = await repo.create(
                project_id=project_id,
                title=title,
                type=type,
                content=content,
                thread_id=thread_id,
            )
            artifact_id = str(artifact.id)

        return (
            f"Artifact saved: '{title}' (type={type}, id={artifact_id})",
            {"id": artifact_id, "title": title, "type": type},
        )

    return create_artifact
