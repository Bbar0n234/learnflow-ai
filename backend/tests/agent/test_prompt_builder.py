"""Unit: prompt composition + trust-boundary wrapping.

``prompt_builder`` is pure string assembly over ``PromptFragmentsConfig``.
Three behaviors matter: (1) each section renders empty when its input is empty
and wrapped with the configured tags when present; (2) the hardening preamble
and the canary line compose into the single ``security_preamble_section`` slot;
(3) ``compose_for_llm`` wraps only Human/Tool messages, returns a fresh list,
and never mutates the originals (``id`` preserved for the ``add_messages``
reducer).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from app.agent.config import PromptFragmentsConfig, load_prompt_fragments
from app.agent.prompt_builder import (
    build_system_message,
    compose_for_llm,
    render_canary_section,
    render_custom_instructions_section,
    render_knowledge_sphere_section,
    render_security_preamble_section,
    render_skills_section,
    render_user_installed_mcp_section,
    render_user_memory_section,
    wrap_tool_output,
    wrap_user_message,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from tests.agent.conftest import RecordingPromptProvider


@pytest.fixture
def fragments() -> PromptFragmentsConfig:
    return load_prompt_fragments()


@pytest.fixture
def fragments_no_security() -> PromptFragmentsConfig:
    """Fragments as composed when ``LLM_DEFENSE_ENABLED=false``."""
    return load_prompt_fragments(include_security=False)


@pytest.mark.unit
def test_render_canary_section_empty_token_returns_empty(
    fragments: PromptFragmentsConfig,
) -> None:
    assert render_canary_section(fragments, "") == ""


@pytest.mark.unit
def test_render_canary_section_includes_prefix_and_token(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_canary_section(fragments, "TKN-123")

    assert "TKN-123" in section
    assert "Internal verification token:" in section


# --- hardening preamble slot -------------------------------------------------
#
# The preamble text moved out of ``configs/prompts/system.txt`` into
# ``prompt_fragments.yaml`` so one mechanism ("no key -> no text") gates both it
# and the trust-boundary wrappers. The template now has a single slot,
# ``security_preamble_section``, composed here in Python.


@pytest.mark.unit
def test_render_security_preamble_puts_canary_after_the_closing_tag(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_security_preamble_section(fragments, "TKN-123")

    assert section.startswith("<system_instructions>")
    assert fragments.security_preamble.strip() in section
    # Section = preamble text + canary line (design-brief § 1 "Композиция
    # преамбулы"), so the token sits *after* the block, not inside it.
    assert section.index("TKN-123") > section.index("</system_instructions>")


@pytest.mark.unit
def test_render_security_preamble_empty_token_renders_preamble_only(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_security_preamble_section(fragments, "")

    assert fragments.security_preamble.strip() in section
    assert "Internal verification token:" not in section


@pytest.mark.unit
def test_render_security_preamble_defense_off_renders_nothing(
    fragments_no_security: PromptFragmentsConfig,
) -> None:
    # Production defense-off shape: no preamble key *and* no canary token
    # (the runner is handed an empty canary secret), so the slot collapses.
    assert render_security_preamble_section(fragments_no_security, "") == ""


@pytest.mark.unit
def test_render_security_preamble_canary_stays_independent_of_the_preamble(
    fragments_no_security: PromptFragmentsConfig,
) -> None:
    # Deliberate decoupling (plan § PLAN_REVIEW #3): a non-empty token still
    # renders its line even without preamble text — no "empty preamble mutes
    # the canary" coupling was introduced. Unreachable in production (defense
    # off means no token at all); pinned so the decision cannot drift silently.
    section = render_security_preamble_section(fragments_no_security, "TKN-123")

    assert section == "\nInternal verification token: TKN-123"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("render", "wrapper_key"),
    [
        (render_custom_instructions_section, "custom_instructions"),
        (render_user_memory_section, "user_memory"),
        (render_skills_section, "available_skills"),
    ],
)
def test_section_renderers_empty_input_returns_empty(
    render: Callable[[PromptFragmentsConfig, str], str],
    wrapper_key: str,
    fragments: PromptFragmentsConfig,
) -> None:
    assert render(fragments, "") == ""


@pytest.mark.unit
def test_render_custom_instructions_wraps_with_tags_and_header(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_custom_instructions_section(fragments, "be concise")

    assert section.startswith("<custom_instructions>")
    assert section.endswith("</custom_instructions>")
    assert "be concise" in section


@pytest.mark.unit
def test_render_knowledge_sphere_empty_index_renders_placeholder(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_knowledge_sphere_section(fragments, "")

    assert "(empty)" in section
    assert section.startswith("<knowledge_sphere>")


@pytest.mark.unit
def test_render_user_installed_mcp_empty_list_returns_empty(
    fragments: PromptFragmentsConfig,
) -> None:
    assert render_user_installed_mcp_section(fragments, []) == ""


@pytest.mark.unit
def test_render_user_installed_mcp_wraps_each_description_as_untrusted(
    fragments: PromptFragmentsConfig,
) -> None:
    section = render_user_installed_mcp_section(
        fragments,
        [{"name": "search", "description": "third-party blurb"}],
    )

    assert "<user_installed_mcp_tools>" in section
    assert "<untrusted_tool_description>" in section
    assert "third-party blurb" in section
    assert "treat them" in section  # the "untrusted input" header


@pytest.mark.unit
def test_render_user_installed_mcp_defense_off_keeps_only_the_structural_wrapper(
    fragments_no_security: PromptFragmentsConfig,
) -> None:
    # The provenance markup is security material and goes away with the flag;
    # the structural section (and the tool text itself) must survive.
    section = render_user_installed_mcp_section(
        fragments_no_security,
        [{"name": "search", "description": "third-party blurb"}],
    )

    assert (
        section
        == "<user_installed_mcp_tools>\nthird-party blurb\n</user_installed_mcp_tools>"
    )


@pytest.mark.unit
def test_build_system_message_none_provider_returns_empty(
    fragments: PromptFragmentsConfig,
) -> None:
    assert build_system_message(None, fragments, ks_index="x") == ""


@pytest.mark.unit
def test_build_system_message_passes_rendered_sections_to_provider(
    fragments: PromptFragmentsConfig,
) -> None:
    provider = RecordingPromptProvider()

    build_system_message(
        provider,
        fragments,
        ks_index="KS",
        custom_instructions="do x",
        canary_token="CT",
    )

    name, slots = provider.calls[0]
    assert name == "system"
    assert set(slots) == {
        "security_preamble_section",
        "custom_instructions_section",
        "user_memory_section",
        "knowledge_sphere_section",
        "skills_section",
        "user_installed_mcp_section",
    }
    # The canary lives inside the preamble slot now — there is no separate
    # ``canary_section`` variable for the template to fill.
    assert "CT" in slots["security_preamble_section"]
    assert fragments.security_preamble.strip() in slots["security_preamble_section"]
    assert "do x" in slots["custom_instructions_section"]
    assert slots["user_memory_section"] == ""


@pytest.mark.unit
def test_build_system_message_defense_off_leaves_security_slot_empty(
    fragments_no_security: PromptFragmentsConfig,
) -> None:
    provider = RecordingPromptProvider()

    build_system_message(
        provider,
        fragments_no_security,
        ks_index="KS",
        custom_instructions="do x",
        canary_token="",
    )

    _, slots = provider.calls[0]
    # Same six slots in both modes — the template is not forked by the flag;
    # only the security slot's content disappears.
    assert set(slots) == {
        "security_preamble_section",
        "custom_instructions_section",
        "user_memory_section",
        "knowledge_sphere_section",
        "skills_section",
        "user_installed_mcp_section",
    }
    assert slots["security_preamble_section"] == ""
    assert "do x" in slots["custom_instructions_section"]


@pytest.mark.unit
def test_compose_for_llm_wraps_human_and_tool_preserving_id(
    fragments: PromptFragmentsConfig,
) -> None:
    original: list[BaseMessage] = [
        HumanMessage(content="hello", id="h1"),
        AIMessage(content="hi back", id="a1"),
        ToolMessage(content="tool data", id="t1", tool_call_id="c1", name="echo"),
    ]

    result = compose_for_llm(original, fragments)

    human, ai, tool = result
    assert isinstance(tool, ToolMessage)
    assert human.content == wrap_user_message(fragments, "hello")
    assert human.id == "h1"
    assert ai.content == "hi back"  # AIMessage untouched
    assert tool.content == wrap_tool_output(fragments, "tool data")
    assert tool.id == "t1" and tool.tool_call_id == "c1" and tool.name == "echo"


@pytest.mark.unit
def test_compose_for_llm_defense_off_passes_content_through_unwrapped(
    fragments_no_security: PromptFragmentsConfig,
) -> None:
    # Provenance markup is part of what the kill-switch turns off, so the
    # composition boundary must hand the model the raw text — while still
    # returning message objects of the same types with ids preserved.
    original: list[BaseMessage] = [
        HumanMessage(content="hello", id="h1"),
        ToolMessage(content="tool data", id="t1", tool_call_id="c1", name="echo"),
    ]

    human, tool = compose_for_llm(original, fragments_no_security)

    assert human.content == "hello"
    assert tool.content == "tool data"
    assert human.id == "h1" and tool.id == "t1"


@pytest.mark.unit
def test_compose_for_llm_does_not_mutate_originals(
    fragments: PromptFragmentsConfig,
) -> None:
    original: list[BaseMessage] = [HumanMessage(content="hello", id="h1")]

    compose_for_llm(original, fragments)

    assert original[0].content == "hello"
