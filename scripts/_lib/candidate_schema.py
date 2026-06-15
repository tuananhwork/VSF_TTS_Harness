"""Code-level guards on judge candidates — the checks we don't trust the LLM
to enforce on itself.

The triage LLM proposes patterns and self-critiques, but "this pattern recurs
across >=2 sessions" is a factual claim we can verify deterministically from
the evidence it cites. Keeping it in code (rather than the prompt) stops the
judge from rubber-stamping its own singletons.

Pure Python. No LLM. Functions do not mutate their inputs.
"""

from __future__ import annotations

from typing import Any


def apply_recurrence_guard(
    candidates: list[dict[str, Any]], *, min_recurrence: int = 2
) -> list[dict[str, Any]]:
    """Reject candidates whose cited evidence has fewer than `min_recurrence`
    distinct sessions. Existing rejections are preserved (kept in the list with
    their reason, per the rejected-stays-visible convention)."""
    out: list[dict[str, Any]] = []
    for c in candidates:
        c = dict(c)
        if not c.get("rejected_reason"):
            distinct = len(set(c.get("evidence", {}).get("session_ids", [])))
            if distinct < min_recurrence:
                c["rejected_reason"] = "low_recurrence"
        out.append(c)
    return out


_BEHAVIOR_TO_SKILL_TYPE = {
    "inefficient": "improvement_lesson",
    "process": "process_macro",
}


def normalize_skill_type(candidate: dict[str, Any]) -> dict[str, Any]:
    """Ensure `skill_type` is set, inferring from `behavior_class` when absent.
    An explicit `skill_type` from the LLM is kept as-is."""
    c = dict(candidate)
    if not c.get("skill_type"):
        c["skill_type"] = _BEHAVIOR_TO_SKILL_TYPE.get(
            c.get("behavior_class", ""), "process_macro"
        )
    return c


def split_accepted(
    candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition into (accepted, rejected) by presence of `rejected_reason`."""
    accepted = [c for c in candidates if not c.get("rejected_reason")]
    rejected = [c for c in candidates if c.get("rejected_reason")]
    return accepted, rejected
