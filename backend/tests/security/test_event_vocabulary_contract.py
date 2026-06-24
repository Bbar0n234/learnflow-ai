"""Cross-side vocabulary contract — verified from the backend (producer) package.

The siem-service cross-side test runs in an environment where the backend ``app``
package is not importable, so it can only AST-scan two hand-listed emitter files
and resolve nothing but string literals — which today is vacuous, because every
real emit site passes a *variable* (imported constant, ``A if cond else B``
selector, or a helper parameter). This test runs where BOTH the producer emitters
and ``siem_contracts`` import, so it resolves every ``event_type=`` the backend
actually emits down to a concrete string and checks two-way completeness against
the shared vocabulary:

1. **Producer ⊆ vocabulary** — every event type the backend emits (resolved
   through imported constants, local ``A if c else B`` selectors, and one level of
   helper-parameter threading) is a member of the canonical vocabulary. This is
   the drift the siem-side scan misses: a producer that hardcodes a literal or
   forks a backend-local constant string the consumer's ``SecurityEvent`` gate
   cannot accept.
2. **Vocabulary ⊆ producer-acceptable** — the real ``make_security_event_processor``
   normalization path produces and publishes a ``SecurityEvent`` for *every*
   vocabulary type. Catches a normalization path that ever starts silently
   dropping a subset of the vocabulary.

The resolver deliberately fails loud (``unresolved``) rather than skipping an
emit expression it cannot reduce: a new emit shape it does not understand must
force a human to extend it, not pass vacuously.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast, get_args

import pytest
import siem_contracts
from app.security_pipeline.processor import make_security_event_processor
from app.security_pipeline.transport import EventTransportHolder, RedisEventTransport
from siem_contracts import SecurityEvent
from siem_contracts.vocabulary import EventType

_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
_VOCAB = frozenset(get_args(EventType))


def _siem_constant(name: str) -> str | None:
    """Resolve a ``siem_contracts``-exported name to its string value, if any."""
    value = getattr(siem_contracts, name, None)
    return value if isinstance(value, str) else None


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = func.args
    return [p.arg for p in (*args.posonlyargs, *args.args, *args.kwonlyargs)]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _has_security_event_true(call: ast.Call) -> bool:
    node = _keyword(call, "security_event")
    return isinstance(node, ast.Constant) and node.value is True


class _EmitterModule:
    """Resolves ``event_type=`` expressions in one backend module to concrete strings.

    Handles the emit shapes that actually occur in the producer: a constant
    imported ``from siem_contracts``, a local ``event_type = A if cond else B``
    selector over such constants, and one level of helper-parameter threading
    (``_check_rate_limit(..., event_type=RATE_LIMIT_*)`` forwarding its parameter
    into the logger call). Any shape it cannot reduce is reported as unresolved
    so the test reds instead of silently under-counting.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.tree = ast.parse(path.read_text(encoding="utf-8"))
        self.import_map: dict[str, str] = self._build_import_map()
        self.functions = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]

    def _build_import_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "siem_contracts"
            ):
                for alias in node.names:
                    value = _siem_constant(alias.name)
                    if value is not None:
                        out[alias.asname or alias.name] = value
        return out

    def _enclosing_function(
        self, target: ast.AST
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        # Innermost wins: among functions containing the node, the one whose body
        # starts latest is the most deeply nested (our emitters are not nested, so
        # there is exactly one, but keep it correct).
        best: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        for func in self.functions:
            if any(node is target for node in ast.walk(func)) and (
                best is None or func.lineno > best.lineno
            ):
                best = func
        return best

    def _local_assignments(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                values = self._resolve(node.value, {}, func)
                if values is not None:
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            out.setdefault(tgt.id, set()).update(values)
        return out

    def _resolve_parameter(
        self,
        param_name: str,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> set[str] | None:
        """Resolve a parameter by inspecting every call to ``func`` in this module."""
        index = _param_names(func).index(param_name)
        resolved: set[str] = set()
        for call in ast.walk(self.tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == func.name
            ):
                continue
            arg = _keyword(call, param_name)
            if arg is None and index < len(call.args):
                arg = call.args[index]
            if arg is None:
                continue
            caller = self._enclosing_function(call)
            local = self._local_assignments(caller) if caller else {}
            values = self._resolve(arg, local, caller)
            if values is None:
                return None
            resolved |= values
        return resolved or None

    def _resolve(
        self,
        node: ast.expr,
        local: dict[str, set[str]],
        func: ast.FunctionDef | ast.AsyncFunctionDef | None,
    ) -> set[str] | None:
        if isinstance(node, ast.Constant):
            return {node.value} if isinstance(node.value, str) else None
        if isinstance(node, ast.IfExp):
            body = self._resolve(node.body, local, func)
            orelse = self._resolve(node.orelse, local, func)
            if body is None or orelse is None:
                return None
            return body | orelse
        if isinstance(node, ast.Name):
            if node.id in self.import_map:
                return {self.import_map[node.id]}
            if node.id in local:
                return local[node.id]
            if func is not None and node.id in _param_names(func):
                return self._resolve_parameter(node.id, func)
            return None
        return None

    def emitted_event_types(self) -> tuple[set[str], list[str]]:
        resolved: set[str] = set()
        unresolved: list[str] = []
        for call in ast.walk(self.tree):
            if not isinstance(call, ast.Call) or not _has_security_event_true(call):
                continue
            event_type = _keyword(call, "event_type")
            if event_type is None:
                # security_event=True with no event_type is a separate producer
                # gap (events silently dropped); not this contract's concern.
                continue
            func = self._enclosing_function(call)
            local = self._local_assignments(func) if func else {}
            values = self._resolve(event_type, local, func)
            if values is None:
                unresolved.append(f"{self.path.name}:{call.lineno}")
            else:
                resolved |= values
        return resolved, unresolved


def _collect_backend_emissions() -> tuple[set[str], list[str]]:
    resolved: set[str] = set()
    unresolved: list[str] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        emitted, blind = _EmitterModule(path).emitted_event_types()
        resolved |= emitted
        unresolved.extend(blind)
    return resolved, unresolved


@pytest.mark.unit
def test_backend_emitted_event_types_are_within_vocabulary() -> None:
    emitted, unresolved = _collect_backend_emissions()

    assert not unresolved, (
        "event_type= expressions the resolver could not reduce to a concrete "
        "string. Either the emit site introduced a new shape (extend the resolver) "
        f"or it should use a siem_contracts vocabulary constant: {unresolved}"
    )
    # Guards against the resolver silently degrading to empty, which would make
    # the ⊆ assertion below vacuously true. Each sentinel exercises a distinct
    # resolution path the siem-side scan cannot follow.
    assert "agent.guard.degraded" in emitted  # direct imported constant
    assert "agent.guard.output.deterministic_hit" in emitted  # `A if cond else B`
    assert "rate_limit.login.exceeded" in emitted  # helper-parameter threading

    outside = emitted - _VOCAB
    assert not outside, (
        f"backend emits event types outside the vocabulary: {sorted(outside)}"
    )


class _SpyTransport:
    def __init__(self) -> None:
        self.published: list[SecurityEvent] = []

    def put_nowait(self, event: SecurityEvent) -> None:
        self.published.append(event)


class _SpyHolder:
    def __init__(self, transport: _SpyTransport) -> None:
        self._transport = transport

    def get(self) -> RedisEventTransport | None:
        return cast(RedisEventTransport, self._transport)


@pytest.mark.unit
def test_producer_normalization_emits_every_vocabulary_type() -> None:
    # The consumer side accepts exactly the vocabulary (its SecurityEvent gate is
    # the EventType Literal). The non-tautological direction worth asserting from
    # the producer is that the real normalization path can *produce* every
    # vocabulary type — drive make_security_event_processor for each and prove a
    # SecurityEvent is published, no type silently dropped or mistyped.
    transport = _SpyTransport()
    processor = make_security_event_processor(
        cast(EventTransportHolder, _SpyHolder(transport))
    )

    for event_type in sorted(_VOCAB):
        processor(
            "logger", "warning", {"security_event": True, "event_type": event_type}
        )

    published = {event.event_type for event in transport.published}
    assert published == _VOCAB
