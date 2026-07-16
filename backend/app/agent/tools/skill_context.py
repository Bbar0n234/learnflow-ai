from __future__ import annotations

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime

from app.agent.tools.skills import _SKILL_NAME_RE

_MAX_CONTENT_LENGTH = 20_000
_MAX_DESCRIPTION_LENGTH = 200
_MAX_DOCUMENTS_PER_SKILL = 20


def _store(runtime: ToolRuntime):  # type: ignore[no-untyped-def]
    if runtime.store is None:
        raise RuntimeError("Skill context tools require a Store but none was provided")
    return runtime.store


def _user_id(runtime: ToolRuntime) -> str:
    if runtime.context is None:
        raise RuntimeError(
            "Skill context tools require AgentContext but none was provided"
        )
    return runtime.context.user_id


def _ns(runtime: ToolRuntime, skill_name: str) -> tuple[str, ...]:
    return ("user", _user_id(runtime), "skill_context", skill_name)


def make_skill_context_tools(skill_names: frozenset[str]) -> list[BaseTool]:
    """Create the get/save/delete_skill_context tools.

    `skill_names` is the startup snapshot of the skill library (see
    `scan_skill_names`), closed over to validate `save_skill_context` against
    unknown/misspelled skill names. `get`/`delete` don't consult it: context
    stored for a skill later removed from the library must stay readable and
    removable (data outlives the skill's presence in the library).
    """

    @tool
    async def get_skill_context(skill_name: str, key: str, runtime: ToolRuntime) -> str:
        """Get the full content of a skill context document.

        Skill context holds per-user documents scoped to a skill (e.g. a
        style profile, samples, preferences). Load the skill first with
        load_skill to see its context index (key: description), then fetch
        a specific document's full content by key here.

        Args:
            skill_name: Name of the skill this document belongs to.
            key: Document key, as listed in the skill's context index.
        """
        store = _store(runtime)
        item = await store.aget(_ns(runtime, skill_name), key)
        if item is None:
            return f"Error: skill context '{key}' not found for skill '{skill_name}'."
        return item.value["content"]

    @tool
    async def save_skill_context(
        skill_name: str,
        key: str,
        description: str,
        content: str,
        runtime: ToolRuntime,
    ) -> str:
        """Save (create or update) a skill context document.

        Use to persist per-user data scoped to a skill: style profiles,
        samples, preferences. Use descriptive keys (e.g. 'profile',
        'sample-habr-sofa').

        Args:
            skill_name: Name of the skill this document belongs to. Must be
                an existing skill in the library.
            key: Document key (lowercase, hyphens).
            description: One-line summary shown in the skill's context index.
            content: Full document content.
        """
        if not _SKILL_NAME_RE.match(skill_name):
            return f"Error: invalid skill name '{skill_name}'."
        if skill_name not in skill_names:
            return f"Error: skill '{skill_name}' not found in library."
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            return (
                f"Error: description exceeds {_MAX_DESCRIPTION_LENGTH} characters "
                f"(got {len(description)})."
            )
        if len(content) > _MAX_CONTENT_LENGTH:
            return (
                f"Error: content exceeds {_MAX_CONTENT_LENGTH} characters "
                f"(got {len(content)})."
            )

        store = _store(runtime)
        ns = _ns(runtime, skill_name)
        existing = await store.aget(ns, key)
        if existing is None:
            documents = await store.asearch(ns, limit=_MAX_DOCUMENTS_PER_SKILL + 1)
            if len(documents) >= _MAX_DOCUMENTS_PER_SKILL:
                return (
                    f"Error: skill '{skill_name}' already has "
                    f"{_MAX_DOCUMENTS_PER_SKILL} context documents (limit reached). "
                    "Delete one before adding another."
                )

        await store.aput(ns, key, {"description": description, "content": content})
        return f"Skill context saved: {skill_name}/{key}"

    @tool
    async def delete_skill_context(
        skill_name: str, key: str, runtime: ToolRuntime
    ) -> str:
        """Delete a skill context document by skill name and key.

        Args:
            skill_name: Name of the skill this document belongs to.
            key: Document key to delete.
        """
        store = _store(runtime)
        await store.adelete(_ns(runtime, skill_name), key)
        return f"Skill context deleted: {skill_name}/{key}"

    return [get_skill_context, save_skill_context, delete_skill_context]
