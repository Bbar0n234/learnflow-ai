"""The ``LLM_DEFENSE_ENABLED`` kill-switch, from env surface to composed prompt.

One operational toggle turns the whole inline LLM defense off. The stream-time
half (no guard is built) is covered by the enforcer/runner suites through the
``SecurityGuard | None`` seam; this file covers what the toggle does to
composition and to startup: which keys ``prompt_fragments.yaml`` yields, what
the system prompt looks like in each mode, and that startup validation of
built-in MCP servers keeps filtering unreachable servers with no guard at all.

The expected key sets are spelled out literally here rather than imported from
``app.agent.config``: the list is the contract from design-brief § 1 ("Гасимые
ключи"), and mirroring the production tuples would make the test agree with the
code by construction instead of checking it. Prod keeps its own grep-able copy
in ``_SECURITY_HEADER_KEYS`` / ``_SECURITY_WRAPPER_KEYS``.

Everything here reads the real ``configs/`` files — the toggle's whole job is to
change what those files produce, so substituting fixtures would test nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app import main as main_module
from app.agent.config import MCPServerConfig, load_prompt_fragments
from app.agent.prompt_builder import build_system_message
from app.agent.security.types import Checkpoint, Verdict
from app.config import Settings
from app.infra.prompt_provider import PromptProvider
from learnflow_testing.fakes import StubGuard
from tests.security.conftest import PREAMBLE_MARKER

_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs"

# design-brief § 1 "Точка врезки" — the six gated keys.
SECURITY_HEADER_KEYS = ("canary_prefix", "user_installed_mcp")
SECURITY_WRAPPER_KEYS = ("user_message", "tool_output", "untrusted_tool_description")

# Kept in both modes — structure, not defense.
STRUCTURAL_HEADER_KEYS = ("custom_instructions",)
STRUCTURAL_WRAPPER_KEYS = (
    "custom_instructions",
    "user_memory",
    "knowledge_sphere",
    "available_skills",
    "user_installed_mcp_tools",
    "document",
)

CANARY_LINE = "Internal verification token:"
MCP_UNTRUSTED_HEADER = "treat them"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No ambient toggle (the Makefile sources .env before pytest)."""
    monkeypatch.delenv("LLM_DEFENSE_ENABLED", raising=False)
    return monkeypatch


@pytest.fixture
def prompt_provider() -> PromptProvider:
    """Real file-backed provider over ``configs/prompts`` (no Langfuse)."""
    return PromptProvider(
        langfuse=None, label="test", cache_ttl=0, prompts_dir=_CONFIGS_DIR / "prompts"
    )


def _render(provider: PromptProvider, *, defense: bool, canary_token: str) -> str:
    fragments = load_prompt_fragments(include_security=defense)
    return build_system_message(
        provider,
        fragments,
        ks_index="KS index",
        skills_index="SK index",
        custom_instructions="be concise",
        user_memory_index="UM index",
        canary_token=canary_token,
        user_installed_mcp_tools=[{"name": "search", "description": "third-party"}],
    )


# --- env surface ------------------------------------------------------------


@pytest.mark.unit
def test_defense_is_enabled_by_default(clean_env: pytest.MonkeyPatch) -> None:
    # Dev behaves as before the kill-switch; production opts out explicitly, so
    # forgetting the .env line costs nothing but the toggle's benefit.
    assert Settings().llm_defense_enabled is True


@pytest.mark.unit
@pytest.mark.parametrize("value", ["false", "0", "False"])
def test_documented_off_values_disable_the_defense(
    clean_env: pytest.MonkeyPatch, value: str
) -> None:
    clean_env.setenv("LLM_DEFENSE_ENABLED", value)

    assert Settings().llm_defense_enabled is False


# --- fragment gating --------------------------------------------------------


@pytest.mark.unit
def test_defense_on_loads_every_security_fragment() -> None:
    fragments = load_prompt_fragments()

    assert fragments.security_preamble.strip().startswith("<system_instructions>")
    assert set(SECURITY_HEADER_KEYS) <= set(fragments.headers)
    assert set(SECURITY_WRAPPER_KEYS) <= set(fragments.wrappers)


@pytest.mark.unit
def test_defense_off_drops_every_security_fragment() -> None:
    fragments = load_prompt_fragments(include_security=False)

    assert fragments.security_preamble == ""
    assert set(SECURITY_HEADER_KEYS).isdisjoint(fragments.headers)
    assert set(SECURITY_WRAPPER_KEYS).isdisjoint(fragments.wrappers)


@pytest.mark.unit
@pytest.mark.parametrize("include_security", [True, False])
def test_structural_fragments_survive_in_both_modes(include_security: bool) -> None:
    # The boundary of the kill-switch: prompt *structure* is never touched, so
    # turning defense off cannot degrade the product behaviour of the agent.
    fragments = load_prompt_fragments(include_security=include_security)

    assert set(STRUCTURAL_HEADER_KEYS) <= set(fragments.headers)
    assert set(STRUCTURAL_WRAPPER_KEYS) <= set(fragments.wrappers)


# ``compose_for_llm`` in both modes is covered one level down, in
# ``tests/agent/test_prompt_builder.py`` (it also pins message types and ids).


# --- composed system prompt -------------------------------------------------


@pytest.mark.unit
def test_defense_on_system_prompt_carries_preamble_and_canary(
    prompt_provider: PromptProvider,
) -> None:
    rendered = _render(prompt_provider, defense=True, canary_token="TKN-TEST")

    assert PREAMBLE_MARKER in rendered
    assert "<untrusted_tool_description>" in rendered
    # Positive twins of the defense-off absence assertions below: without them
    # a header or prefix silently dropped from prompt_fragments.yaml would keep
    # both modes green.
    assert MCP_UNTRUSTED_HEADER in rendered
    assert CANARY_LINE in rendered
    # The canary line follows the closing tag (plan § Open Questions #1).
    assert rendered.index("TKN-TEST") > rendered.index("</system_instructions>")


@pytest.mark.unit
def test_defense_off_system_prompt_drops_all_security_material(
    prompt_provider: PromptProvider,
) -> None:
    # Production defense-off shape: no security keys and no canary secret, so
    # the runner passes an empty token.
    rendered = _render(prompt_provider, defense=False, canary_token="")

    assert "<system_instructions>" not in rendered
    assert PREAMBLE_MARKER not in rendered
    assert CANARY_LINE not in rendered
    assert "<untrusted_tool_description>" not in rendered
    assert MCP_UNTRUSTED_HEADER not in rendered


@pytest.mark.unit
@pytest.mark.parametrize(("defense", "canary_token"), [(True, "TKN-TEST"), (False, "")])
def test_system_prompt_keeps_its_structural_sections_in_both_modes(
    prompt_provider: PromptProvider, defense: bool, canary_token: str
) -> None:
    rendered = _render(prompt_provider, defense=defense, canary_token=canary_token)

    for tag in (
        "<knowledge_sphere>",
        "<available_skills>",
        "<custom_instructions>",
        "<user_memory>",
        "<user_installed_mcp_tools>",
    ):
        assert tag in rendered
    # The third-party tool description survives; only its provenance markup is
    # tied to the toggle.
    assert "third-party" in rendered
    assert "You are LearnFlowAI" in rendered
    # No slot went unfilled: an unsubstituted placeholder would reach the model
    # verbatim (Langfuse compiles unknown variables into the text as-is).
    assert "{{" not in rendered


# --- startup validation of built-in MCP servers -----------------------------
#
# The kill-switch rewrote ``_validate_builtin_mcp``: with no guard the metadata
# blob is not assembled and ``guard.check`` never runs, but the remote fetch and
# the "any error disables the server" fallback stay unconditional. Turning the
# defense off must not quietly turn off the network-level filter with it.
# ``fetch_remote_metadata`` is imported into ``app.main``'s namespace, so the
# network seam is replaced there (same idiom as
# ``tests/personalization/test_mcp_server_service.py``).


def _builtin_server(name: str = "firecrawl") -> dict[str, MCPServerConfig]:
    return {
        name: MCPServerConfig(
            enabled=True,
            transport="http",
            url="https://mcp.example.com",
            allowed_tools=["search"],
        )
    }


def _stub_fetch(monkeypatch: pytest.MonkeyPatch, *, fails: bool = False) -> None:
    async def _fetch(*_args: Any, **_kwargs: Any) -> list[dict[str, str]]:
        if fails:
            raise ConnectionError("remote MCP unreachable")
        return [{"name": "search", "description": "web search"}]

    monkeypatch.setattr(main_module, "fetch_remote_metadata", _fetch)


@pytest.mark.unit
async def test_builtin_mcp_defense_off_still_drops_an_unreachable_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_fetch(monkeypatch, fails=True)

    disabled = await main_module._validate_builtin_mcp(
        _builtin_server(), guard=None, timeout=5
    )

    assert disabled == {"firecrawl"}


@pytest.mark.unit
async def test_builtin_mcp_defense_off_keeps_a_reachable_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_fetch(monkeypatch)

    disabled = await main_module._validate_builtin_mcp(
        _builtin_server(), guard=None, timeout=5
    )

    assert disabled == set()


@pytest.mark.unit
async def test_builtin_mcp_defense_on_drops_a_server_the_guard_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_fetch(monkeypatch)
    guard = StubGuard(Verdict.INJECTION)

    disabled = await main_module._validate_builtin_mcp(
        # StubGuard duck-types SecurityGuard.check; the parameter is annotated
        # with the concrete class, so mypy needs the same waiver the other
        # guard suites use (tests/security/test_runtime_security.py).
        _builtin_server(),
        guard=guard,  # type: ignore[arg-type]
        timeout=5,
    )

    assert disabled == {"firecrawl"}
    # Same fetched metadata that the defense-off case let through: the contrast
    # between the two is what shows the check ran here and not there.
    assert [checkpoint for _, checkpoint in guard.calls] == [Checkpoint.MCP_METADATA]


@pytest.mark.unit
async def test_builtin_mcp_defense_on_keeps_a_server_the_guard_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_fetch(monkeypatch)
    guard = StubGuard(Verdict.CLEAN)

    disabled = await main_module._validate_builtin_mcp(
        # StubGuard duck-types SecurityGuard.check; the parameter is annotated
        # with the concrete class, so mypy needs the same waiver the other
        # guard suites use (tests/security/test_runtime_security.py).
        _builtin_server(),
        guard=guard,  # type: ignore[arg-type]
        timeout=5,
    )

    assert disabled == set()
    assert len(guard.calls) == 1
