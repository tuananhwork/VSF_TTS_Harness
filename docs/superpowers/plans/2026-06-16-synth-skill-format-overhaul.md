# Synth Skill-Format Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `synth.py` (Lượt 3) emit English-only, spec-clean skill folders — pure instruction in SKILL.md, evidence split into `<skill>/evidence/<time>_<hash>/`, `references/` per capability, deterministic assembly with a code-side quality gate.

**Architecture:** One LLM reasoning call (`render_skill`) turns a Vietnamese candidate into strict English JSON (description, capabilities, red flags, golden tests). A pure-Python assembler (`assemble_skill`) deterministically builds the folder from that JSON + raw candidate. A pure-Python validator (`validate_skill`) gates the result. Path A (skill-creator headless) and the old bilingual template path are removed.

**Tech Stack:** Python 3.12, `click`, `jinja2`, `pyyaml`, `pytest`; LLM via `ccs one -p` through `_lib/claude_runner.run_claude_json`.

**Spec:** `docs/superpowers/specs/2026-06-16-synth-skill-format-overhaul-design.md`

**Conventions to follow:**
- Tests import `_lib.*` directly (conftest puts `scripts/` on `sys.path`). LLM calls are never made in tests — inject a fake `runner` or feed a `rendered` dict.
- Jinja env uses `trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True, autoescape=False` (match `render_proposal.py`).
- New assembler templates use **distinct filenames** (`skill_*.j2`) so the legacy `SKILL.md.j2`/`golden_tests.md.j2` keep working until Task 5 deletes them. Every commit leaves `uv run pytest` green.
- Run tests with the project venv: `uv run pytest`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/_lib/skill_render.py` (new) | Stage 1: build the render prompt + call the LLM (`render_skill`). The only reasoning step. |
| `scripts/_lib/skill_assemble.py` (new) | Stage 2: deterministic folder construction (`assemble_skill`, `content_hash`, `decide_split`). |
| `scripts/_lib/skill_validate.py` (new) | Quality gate (`validate_skill`) — returns a list of problems. |
| `scripts/_lib/synth_templates/skill_index.md.j2` (new) | SKILL.md (inline single-capability OR index-of-references). |
| `scripts/_lib/synth_templates/skill_reference.md.j2` (new) | One `references/<slug>.md`. |
| `scripts/_lib/synth_templates/skill_evidence.md.j2` (new) | `evidence/.../evidence.md` provenance. |
| `scripts/_lib/synth_templates/skill_golden.md.j2` (new) | English `golden_tests.md`. |
| `scripts/_lib/synth_templates/skill_script_stub.j2` (new) | Honest `scripts/<name>` stub. |
| `scripts/synth.py` (modify) | Rewire to render→assemble→validate; drop Path A/B; quality-gate section in PROPOSAL. |
| `scripts/_lib/render_proposal.py` (modify) | Remove dead `render_skill_dir` (Task 5). Keep `render_pattern_report`. |
| `scripts/_lib/synth_templates/SKILL.md.j2`, `golden_tests.md.j2` (delete) | Legacy bilingual templates (Task 5). |
| `tests/test_skill_render.py` (new) | Prompt content + injected-runner. |
| `tests/test_skill_assemble.py` (new) | Single vs split, evidence dir, stub, idempotency. |
| `tests/test_skill_validate.py` (new) | Pass + each failure mode. |
| `tests/test_render_proposal.py` (modify) | Drop the 4 `render_skill_dir` tests (Task 5). |
| `README.md` (modify) | Rewrite the "3) Synth" section (Task 6). |

---

## Task 1: Stage 1 — `skill_render.py` (the reasoning call)

**Files:**
- Create: `scripts/_lib/skill_render.py`
- Test: `tests/test_skill_render.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_render.py`:

```python
"""Tests for scripts/_lib/skill_render.py (Stage 1 reasoning call)."""

from __future__ import annotations

from _lib.skill_render import build_render_prompt, render_skill


CANDIDATE = {
    "name": "test-and-report",
    "skill_type": "process_macro",
    "trigger_intent": {"vi": "chạy test rồi báo Teams", "en": "run tests and report"},
    "good_points": ["dùng ToolSearch trước"],
    "weak_points": ["lặp bash 3 lần"],
}


def test_build_render_prompt_includes_candidate_batch_and_rules() -> None:
    prompt = build_render_prompt(CANDIDATE, ["test-and-report", "write-short-prd"])
    # Candidate is embedded so the model can translate/decompose it.
    assert "test-and-report" in prompt
    assert "lặp bash 3 lần" in prompt
    # English-only + instruction-only contract.
    assert "English" in prompt
    assert "STRICT JSON" in prompt
    # Capability cap + single-capability guidance.
    assert "AT MOST 6" in prompt
    # `related` offers only OTHER batch skills, not itself.
    assert "write-short-prd" in prompt
    assert "OTHER SKILLS IN THIS BATCH" in prompt


def test_render_skill_uses_injected_runner() -> None:
    captured = {}

    def fake_runner(prompt, *, timeout):
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        return {"description": "ok", "capabilities": []}

    out = render_skill(CANDIDATE, ["test-and-report"], timeout=42.0, runner=fake_runner)
    assert out == {"description": "ok", "capabilities": []}
    assert captured["timeout"] == 42.0
    assert "test-and-report" in captured["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_skill_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_lib.skill_render'`.

- [ ] **Step 3: Write `skill_render.py`**

Create `scripts/_lib/skill_render.py`:

```python
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


def build_render_prompt(candidate: dict[str, Any], batch_names: list[str]) -> str:
    """Compose the strict-JSON render prompt for one candidate.

    `batch_names` is the slug list of every skill synthesized in this run; the
    model may reference the OTHERS under `related` (we have no global index yet).
    """
    others = [n for n in batch_names if n != candidate.get("name")]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skill_render.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/skill_render.py tests/test_skill_render.py
git commit -m "feat(synth): skill_render — Stage 1 English render prompt + call"
```

---

## Task 2: Quality gate — `skill_validate.py`

**Files:**
- Create: `scripts/_lib/skill_validate.py`
- Test: `tests/test_skill_validate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_validate.py`:

```python
"""Tests for scripts/_lib/skill_validate.py (code-side quality gate)."""

from __future__ import annotations

from pathlib import Path

from _lib.skill_validate import validate_skill


def _make_skill(tmp_path: Path, folder: str, frontmatter: str, body: str) -> Path:
    d = tmp_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return d


def test_validate_passes_clean_skill(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: When to use foo. Use for X.\nmetadata:\n  skill_type: process_macro\n",
        "# foo\n\n## When to use\n\nUse it for X.\n",
    )
    assert validate_skill(d) == []


def test_validate_flags_extra_frontmatter_key(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\nextra: nope\n",
        "# foo\n",
    )
    assert any("frontmatter keys" in p for p in validate_skill(d))


def test_validate_flags_name_folder_mismatch(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: bar\ndescription: d\nmetadata: {}\n",
        "# bar\n",
    )
    assert any("!= folder" in p for p in validate_skill(d))


def test_validate_flags_empty_description(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: ''\nmetadata: {}\n",
        "# foo\n",
    )
    assert any("description" in p for p in validate_skill(d))


def test_validate_flags_birth_history_leak(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n\n## Evidence\n\ngenerated_on: 2026-06-16\n",
    )
    probs = validate_skill(d)
    assert any("birth-history" in p for p in probs)


def test_validate_flags_orphan_reference(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n",
    )
    (d / "references").mkdir()
    (d / "references" / "orphan.md").write_text("# orphan\n", encoding="utf-8")
    assert any("orphan" in p for p in validate_skill(d))


def test_validate_flags_missing_linked_reference(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n\nSee [detail](references/ghost.md).\n",
    )
    assert any("ghost" in p for p in validate_skill(d))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_skill_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_lib.skill_validate'`.

- [ ] **Step 3: Write `skill_validate.py`**

Create `scripts/_lib/skill_validate.py`:

```python
"""Code-side quality gate for an assembled skill folder. No LLM.

Returns a list of human-readable problems; an empty list means the skill passes.
This is the deterministic backstop for the rules we don't trust the render LLM to
keep: spec-clean frontmatter, name==folder, no birth-history leaking back into
SKILL.md, and references that line up with the index.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Substrings that must never appear in SKILL.md body — they are provenance /
# "how I was born", which belongs in evidence/, not in the instructions.
_BIRTH_MARKERS = ("generated_on", "generated_by", "## Evidence", "rút từ session")


def validate_skill(skill_dir: Path) -> list[str]:
    """Validate one assembled skill folder. Empty list == pass."""
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"missing SKILL.md in {skill_dir}"]
    text = skill_md.read_text(encoding="utf-8")

    parts = text.split("---", 2)
    if len(parts) < 3:
        return ["SKILL.md has no YAML frontmatter"]
    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML: {e}"]
    body = parts[2]

    # 1. Exactly the three spec-allowed top-level keys.
    keys = set(front)
    if keys != {"name", "description", "metadata"}:
        problems.append(
            f"frontmatter keys {sorted(keys)} != ['description', 'metadata', 'name']"
        )

    # 2. name matches folder and is a valid slug.
    name = str(front.get("name", ""))
    if name != skill_dir.name:
        problems.append(f"name '{name}' != folder '{skill_dir.name}'")
    if not _SLUG_RE.match(name) or len(name) > 64:
        problems.append(f"name '{name}' is not a valid skill slug")

    # 3. description present, non-empty, <= 1024 chars.
    desc = front.get("description")
    if not isinstance(desc, str) or not (0 < len(desc) <= 1024):
        problems.append("description must be a non-empty string <= 1024 chars")

    # 4. No birth-history leaking into the instructions.
    for marker in _BIRTH_MARKERS:
        if marker in body:
            problems.append(f"SKILL.md leaks birth-history marker: '{marker}'")

    # 5. References line up with the index (no missing links, no orphans).
    refs_dir = skill_dir / "references"
    linked = set(re.findall(r"references/([a-z0-9-]+)\.md", text))
    on_disk = {p.stem for p in refs_dir.glob("*.md")} if refs_dir.exists() else set()
    for miss in sorted(linked - on_disk):
        problems.append(f"index links references/{miss}.md but the file is missing")
    for orphan in sorted(on_disk - linked):
        problems.append(f"references/{orphan}.md exists but is not linked from index")

    return problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skill_validate.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/skill_validate.py tests/test_skill_validate.py
git commit -m "feat(synth): skill_validate — quality gate (frontmatter, no birth-history, refs)"
```

---

## Task 3: Stage 2 — templates + `skill_assemble.py`

**Files:**
- Create: `scripts/_lib/synth_templates/skill_index.md.j2`
- Create: `scripts/_lib/synth_templates/skill_reference.md.j2`
- Create: `scripts/_lib/synth_templates/skill_evidence.md.j2`
- Create: `scripts/_lib/synth_templates/skill_golden.md.j2`
- Create: `scripts/_lib/synth_templates/skill_script_stub.j2`
- Create: `scripts/_lib/skill_assemble.py`
- Test: `tests/test_skill_assemble.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_assemble.py`:

```python
"""Tests for scripts/_lib/skill_assemble.py (deterministic folder builder)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from _lib.skill_assemble import assemble_skill, content_hash, decide_split


CANDIDATE = {
    "name": "test-and-report",
    "skill_type": "process_macro",
    "behavior_class": "process",
    "risk_flags": ["write_action"],
    "evidence": {"session_ids": ["s1", "s2"], "source_files": ["f1.jsonl"]},
    "metrics": {"recurrence": 2, "repeat_rate": 0.1, "failure_rate": 0.0},
    "good_points": ["dùng ToolSearch trước"],
    "weak_points": ["lặp bash 3 lần liên tiếp"],
    "improvement_notes": ["dùng .venv của dự án"],
    "debate": [{"judge": "efficiency", "stance": "approve", "axis_score": 4,
                "argument": "ổn"}],
}

RENDERED_SINGLE = {
    "description": "Run a project's tests and report CI status. Use for CI checks.",
    "when_to_use": "Use when asked to run a project's tests and report CI status.",
    "capabilities": [
        {
            "slug": "run-and-report",
            "title": "Run tests and report",
            "when": "always",
            "steps": ["Find the test tool", "Run pytest", "Report status"],
            "deterministic_script": {
                "name": "run_tests.sh",
                "purpose": "run the project test suite",
                "command": "uv run pytest",
            },
        }
    ],
    "red_flags": ["Re-running the same command after it already ran"],
    "core_lesson": "",
    "golden_tests": [
        {"query": "run tests for project X", "expected": "runs and reports"},
        {"query": "check CI status", "expected": "reports pass/fail"},
        {"query": "test and tell Teams", "expected": "runs then notifies"},
    ],
    "related": [],
}

RENDERED_MULTI = {
    **RENDERED_SINGLE,
    "capabilities": [
        {"slug": "run-tests", "title": "Run tests", "when": "first",
         "steps": ["a", "b"]},
        {"slug": "report-teams", "title": "Report to Teams", "when": "after",
         "steps": ["c", "d"]},
    ],
}

NOW = datetime(2026, 6, 16, 9, 30)


def test_decide_split_on_capability_count() -> None:
    assert decide_split(RENDERED_SINGLE) is False
    assert decide_split(RENDERED_MULTI) is True


def test_assemble_single_capability_inline_no_references(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    assert d.name == "test-and-report"
    assert not (d / "references").exists()
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "## When to use" in skill
    assert "Run pytest" in skill                 # steps inline
    assert "name: test-and-report" in skill
    assert "skill_type: process_macro" in skill
    # Pure instruction: no provenance leaks into SKILL.md.
    assert "s1" not in skill and "generated_on" not in skill


def test_assemble_writes_honest_script_stub(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    stub = (d / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
    assert "STUB" in stub                        # honest: marked not-yet-verified
    assert "uv run pytest" in stub


def test_assemble_writes_evidence_with_raw_vietnamese(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    ev_dirs = list((d / "evidence").iterdir())
    assert len(ev_dirs) == 1
    assert ev_dirs[0].name == f"20260616-0930_{content_hash(skill)}"
    ev = (ev_dirs[0] / "evidence.md").read_text(encoding="utf-8")
    assert "s1" in ev                            # session ids live here
    assert "lặp bash 3 lần liên tiếp" in ev      # raw VI evidence preserved
    assert "efficiency" in ev                    # debate verdict


def test_assemble_multi_capability_splits_references(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_MULTI,
                       output_dir=tmp_path, now=NOW)
    refs = sorted(p.name for p in (d / "references").glob("*.md"))
    assert refs == ["report-teams.md", "run-tests.md"]
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "references/run-tests.md" in skill
    assert "references/report-teams.md" in skill
    # Index does not inline the steps when split.
    detail = (d / "references" / "run-tests.md").read_text(encoding="utf-8")
    assert "Run tests" in detail


def test_assemble_evidence_idempotent_on_same_content(tmp_path: Path) -> None:
    assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                   output_dir=tmp_path, now=NOW)
    # Second run, LATER time, identical content → no second evidence dir.
    later = datetime(2026, 6, 16, 10, 45)
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=later)
    assert len(list((d / "evidence").iterdir())) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_skill_assemble.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_lib.skill_assemble'`.

- [ ] **Step 3: Create the five templates**

Create `scripts/_lib/synth_templates/skill_index.md.j2`:

```jinja
---
name: {{ name }}
description: {{ description | tojson }}
metadata:
  skill_type: {{ skill_type }}
  risk_flags: {{ risk_flags | tojson }}
---

# {{ name }}

## When to use

{{ when_to_use }}
{% if core_lesson %}

## Core lesson

{{ core_lesson }}
{% endif %}

## Capabilities
{% if split %}

| Capability | When | Detail |
| --- | --- | --- |
{% for cap in capabilities %}
| {{ cap.title }} | {{ cap.when }} | [`references/{{ cap.slug }}.md`](references/{{ cap.slug }}.md) |
{% endfor %}
{% else %}
{% set cap = capabilities[0] %}

**{{ cap.title }}** — {{ cap.when }}

{% for step in cap.steps %}
{{ loop.index }}. {{ step }}
{% endfor %}
{% if cap.deterministic_script %}

Deterministic step → run `scripts/{{ cap.deterministic_script.name }}`
({{ cap.deterministic_script.purpose }}).
{% endif %}
{% endif %}
{% if red_flags %}

## Red flags — STOP

{% for rf in red_flags %}
- {{ rf }}
{% endfor %}
{% endif %}
{% if related %}

## Related skills

{% for r in related %}
- `{{ r }}`
{% endfor %}
{% endif %}
```

Create `scripts/_lib/synth_templates/skill_reference.md.j2`:

```jinja
# {{ cap.title }}

**When:** {{ cap.when }}

## Steps

{% for step in cap.steps %}
{{ loop.index }}. {{ step }}
{% endfor %}
{% if cap.deterministic_script %}

## Script

Deterministic — run `scripts/{{ cap.deterministic_script.name }}`
({{ cap.deterministic_script.purpose }}).
{% endif %}
```

Create `scripts/_lib/synth_templates/skill_evidence.md.j2`:

```jinja
# Evidence — {{ name }}

> Provenance for this skill draft. NOT part of the skill instructions.

- skill_type: {{ skill_type }}
- behavior_class: {{ behavior_class }}
- generated_on: {{ generated_on }}
- skill_md_hash: {{ hash8 }}

## Source sessions

{% for sid in session_ids %}
- `{{ sid }}`
{% endfor %}
{% if source_files %}

## Source files

{% for sf in source_files %}
- `{{ sf }}`
{% endfor %}
{% endif %}

## Metrics

{% if metrics %}
- recurrence: {{ metrics.recurrence }}
- repeat_rate: {{ metrics.repeat_rate }}
- failure_rate: {{ metrics.failure_rate }}
{% else %}
_None recorded._
{% endif %}

## Good points (raw)

{% for g in good_points %}
- {{ g }}
{% endfor %}

## Weak points (raw)

{% for w in weak_points %}
- {{ w }}
{% endfor %}

## Improvement notes (raw)

{{ improvement_notes }}
{% if debate %}

## Debate verdicts

{% for v in debate %}
- **{{ v.judge }}** [{{ v.stance }}{% if v.axis_score is not none %}, {{ v.axis_score }}/5{% endif %}]: {{ v.argument or v.error }}
{% endfor %}
{% endif %}
```

Create `scripts/_lib/synth_templates/skill_golden.md.j2`:

```jinja
# Golden tests — {{ name }}

3 sample queries built from evidence. Run them manually in Claude Cowork and
verify the skill triggers and the output meets expectation.

{% for t in golden_tests %}
## Test {{ loop.index }}

**Query:**
{{ t.query }}

**Expected:**
{{ t.expected }}

{% endfor %}
```

Create `scripts/_lib/synth_templates/skill_script_stub.j2`:

```jinja
#!/usr/bin/env bash
# STUB — generated by Pattern synth. NOT yet verified to run.
# Purpose: {{ purpose }}
# Intended command:
#   {{ command }}
#
# TODO: review and complete this script before relying on it.
set -euo pipefail

{{ command }}
```

- [ ] **Step 4: Write `skill_assemble.py`**

Create `scripts/_lib/skill_assemble.py`:

```python
"""Stage 2 of synth: deterministically build a skill folder from a candidate plus
the Stage-1 rendered content. No LLM here — pure file/string construction, so the
whole thing is unit-testable.

Layout produced under `<output_dir>/<slug>/`:
  SKILL.md                          # instruction-only (inline or index)
  references/<slug>.md              # only when >1 capability
  scripts/<name>                    # only for capabilities with a deterministic step
  golden_tests.md
  evidence/<YYYYMMDD-HHMM>_<hash8>/evidence.md   # all provenance
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from _lib.candidate_schema import slugify_skill_name

_TEMPLATES_DIR = Path(__file__).parent / "synth_templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def content_hash(text: str) -> str:
    """First 8 hex chars of sha256 — identifies one SKILL.md revision."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def decide_split(rendered: dict[str, Any]) -> bool:
    """Split into references/ when the skill has more than one capability."""
    return len(rendered.get("capabilities") or []) > 1


def _as_block(value: Any) -> str:
    """Normalize a str | list into a markdown block for evidence."""
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value or "").strip()


def _evidence_hash_present(evidence_dir: Path, hash8: str) -> bool:
    if not evidence_dir.exists():
        return False
    return any(
        p.is_dir() and p.name.endswith(f"_{hash8}") for p in evidence_dir.iterdir()
    )


def assemble_skill(
    *,
    candidate: dict[str, Any],
    rendered: dict[str, Any],
    output_dir: Path,
    now: datetime,
) -> Path:
    """Build (or refresh) the skill folder for one candidate. Returns its path.

    `now` is injected (not read from the clock) so output is reproducible in tests.
    """
    name = slugify_skill_name(candidate["name"])
    skill_dir = output_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_type = candidate.get("skill_type", "process_macro")
    capabilities = rendered.get("capabilities") or []
    split = decide_split(rendered)

    # --- SKILL.md (inline single capability OR index of references) ---
    skill_md = _env.get_template("skill_index.md.j2").render(
        name=name,
        description=rendered["description"],
        skill_type=skill_type,
        risk_flags=candidate.get("risk_flags") or [],
        when_to_use=rendered.get("when_to_use", ""),
        core_lesson=rendered.get("core_lesson") or "",
        capabilities=capabilities,
        split=split,
        red_flags=rendered.get("red_flags") or [],
        related=rendered.get("related") or [],
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # --- references/<slug>.md (only when split) ---
    if split:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for cap in capabilities:
            (refs_dir / f"{cap['slug']}.md").write_text(
                _env.get_template("skill_reference.md.j2").render(cap=cap),
                encoding="utf-8",
            )

    # --- scripts/<name> honest stubs for deterministic capabilities ---
    scripts = [
        c["deterministic_script"]
        for c in capabilities
        if c.get("deterministic_script")
    ]
    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for sc in scripts:
            (scripts_dir / sc["name"]).write_text(
                _env.get_template("skill_script_stub.j2").render(
                    purpose=sc.get("purpose", ""), command=sc.get("command", "")
                ),
                encoding="utf-8",
            )

    # --- golden_tests.md ---
    (skill_dir / "golden_tests.md").write_text(
        _env.get_template("skill_golden.md.j2").render(
            name=name, golden_tests=rendered.get("golden_tests") or []
        ),
        encoding="utf-8",
    )

    # --- evidence/<time>_<hash>/evidence.md (skip if this content already logged) ---
    hash8 = content_hash(skill_md)
    evidence_dir = skill_dir / "evidence"
    if not _evidence_hash_present(evidence_dir, hash8):
        target = evidence_dir / f"{now.strftime('%Y%m%d-%H%M')}_{hash8}"
        target.mkdir(parents=True, exist_ok=True)
        ev = candidate.get("evidence", {}) or {}
        (target / "evidence.md").write_text(
            _env.get_template("skill_evidence.md.j2").render(
                name=name,
                skill_type=skill_type,
                behavior_class=candidate.get("behavior_class", ""),
                generated_on=now.strftime("%Y-%m-%d"),
                hash8=hash8,
                session_ids=ev.get("session_ids", []),
                source_files=ev.get("source_files", []),
                metrics=candidate.get("metrics"),
                good_points=candidate.get("good_points") or [],
                weak_points=candidate.get("weak_points") or [],
                improvement_notes=_as_block(candidate.get("improvement_notes")),
                debate=candidate.get("debate") or [],
            ),
            encoding="utf-8",
        )

    return skill_dir
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_skill_assemble.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add scripts/_lib/skill_assemble.py scripts/_lib/synth_templates/skill_*.j2 tests/test_skill_assemble.py
git commit -m "feat(synth): skill_assemble + English templates (inline/index, evidence split)"
```

---

## Task 4: Rewire `synth.py` to render → assemble → validate

**Files:**
- Modify: `scripts/synth.py` (replace Path A/B helpers + `_synthesize_one` + `main` loop + PROPOSAL emit)

- [ ] **Step 1: Replace imports**

In `scripts/synth.py`, replace the existing import block:

```python
from _lib.claude_runner import (  # noqa: E402
    ClaudeRunError,
    run_claude,
    run_claude_json,
)
from _lib.candidate_schema import slugify_skill_name  # noqa: E402
from _lib.render_proposal import build_skill_description, render_skill_dir  # noqa: E402
```

with:

```python
from datetime import datetime  # noqa: E402

from _lib.candidate_schema import normalize_skill_name  # noqa: E402
from _lib.skill_render import render_skill  # noqa: E402
from _lib.skill_assemble import assemble_skill  # noqa: E402
from _lib.skill_validate import validate_skill  # noqa: E402
```

- [ ] **Step 2: Delete the dead Path A/B prompt helpers**

Delete the entire `_path_a_prompt(...)` function and the entire `_path_b_fill_prompt(...)` function from `scripts/synth.py`. (They span from `def _path_a_prompt` through the end of `_path_b_fill_prompt`'s return string.)

- [ ] **Step 3: Replace `_synthesize_one`**

Replace the whole `_synthesize_one(...)` function with:

```python
def _synthesize_one(
    candidate: dict, batch_names: list[str], out_dir: Path, timeout: float,
    now: datetime,
) -> dict:
    """Render (LLM) → assemble (code) → validate (code). Returns candidate plus
    the quality-gate result under `synth_problems`."""
    rendered = render_skill(candidate, batch_names, timeout=timeout)
    skill_dir = assemble_skill(
        candidate=candidate, rendered=rendered, output_dir=out_dir, now=now,
    )
    problems = validate_skill(skill_dir)
    if problems:
        click.echo(f"  ! quality gate flagged {skill_dir.name}: {'; '.join(problems)}")
    return {**candidate, "synth_problems": problems}
```

- [ ] **Step 4: Replace the `main()` body**

Replace the body of `main(...)` (everything after the `@click` decorators' function signature line) with:

```python
def main(candidates_path: Path, top: int, timeout: float) -> None:
    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"skills_{today}_proposal"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    accepted = [c for c in all_candidates if not c.get("rejected_reason")]
    top_n = [normalize_skill_name(c) for c in accepted[:top]]
    batch_names = [c["name"] for c in top_n]
    click.echo(f"[synth] {len(top_n)} candidates to synthesize")

    now = datetime.now()
    results: list[dict] = []
    for c in top_n:
        click.echo(f"[synth] -> {c['name']}")
        results.append(_synthesize_one(c, batch_names, out_dir, timeout, now))

    (out_dir / "_proposal_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _emit_accept_py(out_dir, [c["name"] for c in results])

    from _lib.render_proposal import render_pattern_report
    proposal_md = render_pattern_report(
        date=today,
        date_range=str(candidates_path.parent.name),
        sessions_scanned=0,
        clusters=[],
        candidates=results,
    )
    gate_lines = [
        f"- `{c['name']}`: " + ("OK" if not c.get("synth_problems")
                                 else "; ".join(c["synth_problems"]))
        for c in results
    ]
    proposal_md += "\n## Synth quality gate\n\n" + "\n".join(gate_lines) + "\n"
    (out_dir / "PROPOSAL.md").write_text(proposal_md, encoding="utf-8")
    click.echo(f"[synth] done -> {out_dir}")
```

- [ ] **Step 5: Update the module docstring**

Replace the top-of-file docstring (lines describing Path A / Path B) with:

```python
"""Lượt 3 — Skill synthesis.

For each top-N accepted candidate:
  1. render_skill (LLM, the one reasoning call) → English skill content as JSON.
  2. assemble_skill (code) → deterministic skill folder (SKILL.md, references/,
     scripts/ stubs, golden_tests.md, evidence/<time>_<hash>/).
  3. validate_skill (code) → quality gate; problems surface in PROPOSAL.md.

Writes PROPOSAL.md + accept.py under data/skills_<date>_proposal/.

Usage:
    python scripts/synth.py --candidates data/judge_<date>/candidate_skills.json \\
        [--top 3] [--timeout 120]
"""
```

- [ ] **Step 6: Verify nothing else imports the removed symbols**

Run: `uv run python -c "import ast,sys; sys.path.insert(0,'scripts'); import synth"`
Expected: no error (imports resolve).

Also run: `git grep -n "render_skill_dir\|_path_a_prompt\|_path_b_fill_prompt\|build_skill_description" -- scripts/ e2e.py`
Expected: matches ONLY in `scripts/_lib/render_proposal.py` (the def, removed in Task 5). If `e2e.py` references any, note it for Task 6. If `build_skill_description` shows other users, leave it; otherwise it is removed in Task 5.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — existing `test_render_proposal.py` (still has the 4 legacy `render_skill_dir` tests, still green because the legacy templates/function are untouched), plus the new modules.

- [ ] **Step 8: Commit**

```bash
git add scripts/synth.py
git commit -m "feat(synth): rewire to render->assemble->validate, drop Path A/B"
```

---

## Task 5: Remove legacy `render_skill_dir`, its tests, and old templates

**Files:**
- Modify: `scripts/_lib/render_proposal.py` (delete `render_skill_dir`; delete `build_skill_description` only if Task 4 Step 6 showed no other users)
- Modify: `tests/test_render_proposal.py` (delete the 4 `render_skill_dir` tests)
- Delete: `scripts/_lib/synth_templates/SKILL.md.j2`
- Delete: `scripts/_lib/synth_templates/golden_tests.md.j2`

- [ ] **Step 1: Delete the legacy tests**

In `tests/test_render_proposal.py`, delete these four test functions and the now-unused imports `from pathlib import Path` / `from _lib.render_proposal import render_skill_dir` / `import yaml` (keep `import yaml` only if another remaining test uses it — it does not, so remove it):
- `test_render_skill_dir_writes_skill_and_golden_tests`
- `test_render_skill_dir_frontmatter_conforms_to_agent_skills_spec`
- `test_render_skill_dir_improvement_lesson_surfaces_weak_and_improve`
- `test_render_skill_dir_process_macro_renders_ordered_flow`

The file should retain only `test_pattern_report_lists_candidates_and_clusters` and its `from _lib.render_proposal import render_pattern_report` import.

- [ ] **Step 2: Delete `render_skill_dir` from `render_proposal.py`**

Delete the entire `render_skill_dir(...)` function and the now-unused module-level setup that only it used: `from pathlib import Path`, `from jinja2 import FileSystemLoader`, `_TEMPLATES_DIR`, `_file_env`. Keep `build_skill_description` and `render_pattern_report` and the `_env`/`_PATTERN_REPORT_TMPL` they use.

If Task 4 Step 6 showed `build_skill_description` has no other users, also delete it.

- [ ] **Step 3: Delete the legacy templates**

```bash
git rm scripts/_lib/synth_templates/SKILL.md.j2 scripts/_lib/synth_templates/golden_tests.md.j2
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — `test_render_proposal.py` now has 1 test; all new tests green.

- [ ] **Step 5: Confirm no dangling references**

Run: `git grep -n "render_skill_dir\|SKILL.md.j2\|golden_tests.md.j2" -- scripts/ tests/`
Expected: no matches (the assembler uses `skill_index.md.j2` / `skill_golden.md.j2`).

- [ ] **Step 6: Commit**

```bash
git add scripts/_lib/render_proposal.py tests/test_render_proposal.py
git commit -m "refactor(synth): drop legacy render_skill_dir + bilingual templates"
```

---

## Task 6: README + end-to-end smoke + final verification

**Files:**
- Modify: `README.md` (the "### 3) Synth" section)
- Check: `e2e.py`

- [ ] **Step 1: Rewrite the README Synth section**

In `README.md`, replace the body of `### 3) Synth — sinh skill draft + proposal` (keep the heading and the `uv run` command block) with:

```markdown
Mỗi accepted candidate đi qua 2 stage:
- **render_skill** (LLM, 1 call): dịch candidate (VI) → nội dung skill **English**
  (description, capabilities, red flags, golden tests). Đây là phần cần reasoning.
- **assemble_skill** (code, deterministic): dựng folder skill:
  - `SKILL.md` — **chỉ chỉ dẫn**, English; 1 năng lực → flow inline, nhiều năng lực
    → index + `references/<slug>.md` mỗi năng lực.
  - `scripts/<name>` — stub trung thực cho bước deterministic (không bịa logic).
  - `evidence/<time>_<hash>/evidence.md` — toàn bộ provenance (session_ids,
    good/weak/improvement gốc, debate, metrics). **Không** nằm trong SKILL.md.
  - `golden_tests.md`.
- **validate_skill** (code): quality gate — frontmatter đúng 3 key, name==folder,
  không leak birth-history, references khớp index. Vi phạm được cờ trong
  `## Synth quality gate` của PROPOSAL.md.

Output: `data/skills_<date>_proposal/{PROPOSAL.md, accept.py, <skill-name>/...}`.
`accept.py` copy nguyên folder skill **kèm** `evidence/`.
```

- [ ] **Step 2: Check `e2e.py` for stale synth assumptions**

Run: `git grep -n "synth\|render_skill_dir\|Path A\|Path B\|SKILL.md.j2" -- e2e.py`
Expected: only invocation of `scripts/synth.py` via CLI (which is unchanged: `--candidates --top --timeout`). If `e2e.py` asserts on old output shape (e.g. inline Evidence section), update that assertion to check `SKILL.md` exists and `evidence/` dir exists instead. If nothing references removed internals, no change.

- [ ] **Step 3: Full test run**

Run: `uv run pytest -q`
Expected: PASS (all tests green).

- [ ] **Step 4: Lint-free import check of the whole scripts package**

Run: `uv run python -c "import sys; sys.path.insert(0,'scripts'); import synth, _lib.skill_render, _lib.skill_assemble, _lib.skill_validate, _lib.render_proposal; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add README.md e2e.py
git commit -m "docs(synth): README step 3 = render->assemble->validate; e2e check"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- English-only SKILL.md → Task 1 (render prompt) + Task 3 (templates). ✔
- Evidence split to `<skill>/evidence/<time>_<hash>/` → Task 3 (`assemble_skill`). ✔
- Deterministic assembler primary, Path A dropped → Task 4. ✔
- references/ split by capability count → Task 3 (`decide_split`, templates) + Task 1 (≤6 cap rule). ✔
- scripts/ honest stub for deterministic steps → Task 3 (`skill_script_stub.j2`). ✔
- Quality gate (frontmatter purity, no birth-history, refs) → Task 2 (`validate_skill`), wired in Task 4. ✔
- No birth-history in SKILL.md (no generated_by/on, no Evidence section) → Task 3 templates + Task 2 markers. ✔
- accept.py copies evidence/ → already `shutil.copytree` (whole tree); README note in Task 6. ✔
- Legacy bilingual path removed → Task 5. ✔
- Deferred (model-routing, hooks, global related index) → out of scope per spec; not in plan. ✔

**Placeholder scan:** No "TBD"/"implement later". The only `TODO` is inside the generated `skill_script_stub.j2` — intentional, honest-stub content.

**Type consistency:** `render_skill(candidate, batch_names, *, timeout, runner)` returns the dict consumed by `assemble_skill(candidate=, rendered=, output_dir=, now=)`. `validate_skill(skill_dir) -> list[str]`. `decide_split(rendered)`/`content_hash(text)` names match across Task 3 code and tests. `normalize_skill_name` (used in Task 4) and `slugify_skill_name` (used in Task 3) both exist in `candidate_schema.py`. Template filenames (`skill_index.md.j2`, `skill_reference.md.j2`, `skill_evidence.md.j2`, `skill_golden.md.j2`, `skill_script_stub.j2`) match `assemble_skill`'s `get_template` calls.
