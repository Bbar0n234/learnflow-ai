from __future__ import annotations

from fuzzysearch import find_near_matches

from app.agent.tools.store_helpers import format_index as _generic_format_index

SPHERE_NAMESPACE_PREFIX = ("project",)


def build_namespace(project_id: str) -> tuple[str, ...]:
    return ("project", project_id, "sphere")


def section_key(section_id: str) -> str:
    return f"section:{section_id}"


def fuzzy_find_and_replace(
    document: str,
    target: str,
    replacement: str,
    threshold: float = 0.85,
) -> tuple[str, bool, str | None, float]:
    """Fuzzy find target in document and replace with replacement.

    Returns: (new_document, success, found_text, similarity)
    """
    if not target or not document:
        return document, False, None, 0.0

    # Short strings (<10 chars) — exact match only
    if len(target) < 10:
        if target in document:
            idx = document.index(target)
            new_doc = document[:idx] + replacement + document[idx + len(target) :]
            return new_doc, True, target, 1.0
        return document, False, None, 0.0

    # Adaptive distance
    max_distance = max(1, int(len(target) * (1 - threshold)))
    if len(target) > 100:
        max_distance = min(max_distance, 15)

    matches = find_near_matches(target, document, max_l_dist=max_distance)
    if not matches:
        return document, False, None, 0.0

    match = matches[0]
    similarity = max(0.0, 1 - (match.dist / len(target)))

    new_document = document[: match.start] + replacement + document[match.end :]
    return new_document, True, match.matched, similarity


def format_index(items: list) -> str:
    """Format store items as Knowledge Sphere index for system message."""
    return _generic_format_index(
        items,
        title="Knowledge Sphere",
        key_fn=lambda i: i.key.removeprefix("section:"),
    )
