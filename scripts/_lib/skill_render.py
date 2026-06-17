"""Stage 1 of synth: the single LLM call that renders a behavior candidate into
clean, English-only skill content.

Everything requiring judgment lives here — translation from Vietnamese, splitting
the behavior into capabilities, writing instruction prose, red flags, and golden
tests. Folder construction is deterministic and lives in skill_assemble.py.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from _lib.claude_runner import run_claude_json

_MAX_CAPABILITIES = 6

# Only the fields that inform the skill's CONTENT. Everything else on the
# enriched candidate (debate verdicts, evidence ids, metrics, scores,
# consolidator notes) is pipeline bookkeeping the render prompt explicitly tells
# the model NOT to emit — so we drop it here to cut distractor noise.
_RENDER_FIELDS = (
    "name", "skill_type", "behavior_class", "trigger_intent",
    "action_template", "good_points", "weak_points", "improvement_notes",
    "golden_tests", "risk_flags", "core_lesson",
)


def _project_for_render(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep only the content-bearing fields (see _RENDER_FIELDS)."""
    return {k: candidate[k] for k in _RENDER_FIELDS if k in candidate}


def build_render_prompt(candidate: dict[str, Any], batch_names: list[str]) -> str:
    """Compose the strict-JSON render prompt for one candidate.

    `batch_names` is the slug list of every skill synthesized in this run; the
    model may reference the OTHERS under `related` (we have no global index yet).
    """
    others = [n for n in batch_names if n != candidate.get("name")]
    candidate = _project_for_render(candidate)
    return f"""You are turning an observed-behavior skill candidate into a clean,
English-only Agent Skill. Output STRICT JSON only — no prose, no markdown fences.

The candidate fields may be in Vietnamese; translate EVERYTHING to English.
A skill is INSTRUCTIONS ONLY: it states WHEN to use it and, per capability, the
ordered steps. Do NOT include evidence, session ids, metrics, or any note about
how the skill was generated — that lives elsewhere.

CANDIDATE:
{json.dumps(candidate, ensure_ascii=False, indent=2)}

OTHER SKILLS IN THIS BATCH (allowed values for `related`):
{json.dumps(others, ensure_ascii=False)}

Return JSON with EXACTLY this shape:
{{
  "description": "<English. What it does + WHEN to use it + trigger keywords. <=1024 chars>",
  "when_to_use": "<1-2 English sentences expanding the trigger>",
  "capabilities": [
    {{
      "slug": "<kebab-case>",
      "title": "<short English title>",
      "when": "<when this capability applies>",
      "steps": ["<ordered English step>", "..."],
      "deterministic_script": {{"name": "run_x.sh", "purpose": "...", "command": "..."}}
    }}
  ],
  "red_flags": ["<STOP signal: about to repeat a past mistake or trigger a side-effect>"],
  "core_lesson": "<only if skill_type is improvement_lesson, else empty string>",
  "golden_tests": [
    {{"query": "<English user request>", "expected": "<English expected behavior>"}}
  ],
  "related": {json.dumps(others, ensure_ascii=False)}
}}

Rules:
- Decompose into AT MOST {_MAX_CAPABILITIES} capabilities. If the behavior is one
  coherent procedure, use a SINGLE capability so the skill stays one file.
- Add `deterministic_script` ONLY to a capability whose step is mechanical
  (e.g. running tests, validating a file). Omit the key otherwise — judgment
  steps stay prose, never a script.
- Return EXACTLY 3 golden_tests.
- `related` must be a subset of the batch list above, or an empty list.
"""


def render_skill(
    candidate: dict[str, Any],
    batch_names: list[str],
    *,
    timeout: float = 180.0,
    runner: Callable[..., Any] = run_claude_json,
) -> dict[str, Any]:
    """One LLM call → reasoned English skill content as a dict.

    `runner` is injectable so tests never hit the network.
    """
    return runner(build_render_prompt(candidate, batch_names), timeout=timeout)
