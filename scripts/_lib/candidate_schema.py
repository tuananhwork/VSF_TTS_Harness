"""Code-level guards on judge candidates — the checks we don't trust the LLM
to enforce on itself.

The triage LLM proposes patterns and self-critiques, but "this pattern recurs
across >=2 sessions" is a factual claim we can verify deterministically from
the evidence it cites. Keeping it in code (rather than the prompt) stops the
judge from rubber-stamping its own singletons.

Pure Python. No LLM. Functions do not mutate their inputs.
"""

from __future__ import annotations

import re
from typing import Any


_NAME_INVALID = re.compile(r"[^a-z0-9-]+")


def slugify_skill_name(raw: str, *, max_len: int = 64) -> str:
    """Coerce a raw candidate name into a spec-valid Agent Skills `name`.

    The Agent Skills spec (https://agentskills.io/specification) requires the
    `name` to be lowercase `a-z`/`0-9`/`-` only, with no leading, trailing, or
    consecutive hyphens, at most 64 chars, and matching the skill folder name.
    The judge LLM emits snake_case, so this is the single place we normalize.
    Idempotent: slugifying an already-valid name returns it unchanged.
    """
    s = (raw or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = _NAME_INVALID.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    s = s[:max_len].rstrip("-")
    return s or "unnamed-skill"


def normalize_skill_name(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `candidate` with a spec-valid `name`. Does not mutate."""
    c = dict(candidate)
    c["name"] = slugify_skill_name(c.get("name", ""))
    return c


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
