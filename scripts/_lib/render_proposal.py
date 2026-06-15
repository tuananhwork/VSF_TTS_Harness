"""Jinja2 renderers for Lượt 2 pattern_report.md and Lượt 3 PROPOSAL.md."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment


_env = Environment(
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


_PATTERN_REPORT_TMPL = _env.from_string("""\
# Pattern report — {{ date }}

| Field | Value |
| --- | --- |
| Date range | {{ date_range }} |
| Sessions scanned | {{ sessions_scanned }} |
| Clusters found | {{ clusters | length }} |
| Candidates emitted | {{ candidates | length }} |
| Candidates passed critique | {{ accepted | length }} |

## Clusters

{% for cl in clusters %}
### Cluster {{ loop.index }} ({{ cl.behavior_class_hint }})
- recurrence: {{ cl.recurrence }}, retry_rate: {{ cl.retry_rate }}, correction_rate: {{ cl.correction_rate }}
- representative tools: `{{ cl.representative_tools | join(", ") }}`
- tool_sequence: {% for seq in cl.tool_sequence_per_session %}`{{ seq | join(" → ") }}`{% if not loop.last %} | {% endif %}{% endfor %}

- titles: {{ cl.titles | join(" | ") }}
- sessions: {{ cl.process_names | join(", ") }}

{% endfor %}

## Top candidates (passed critique)

{% if accepted %}
{% for c in accepted %}
### {{ loop.index }}. `{{ c.name }}` — {{ c.skill_type }} ({{ c.behavior_class }})
- Trigger (VI): {{ c.trigger_intent.vi }}
- Trigger (EN): {{ c.trigger_intent.en }}
- Score total: {{ c._score_total }}
- Flow (action template):
{% for step in c.action_template %}
  {{ step.step }}. `{{ step.tool }}` ← {{ step.input_shape }}
{% endfor %}
{% if c.good_points %}
- Điểm tốt / Good:
{% for g in c.good_points %}
  - {{ g }}
{% endfor %}
{% endif %}
{% if c.weak_points %}
- Điểm chưa tốt / Weak:
{% for w in c.weak_points %}
  - {{ w }}
{% endfor %}
{% endif %}
{% if c.improvement_notes %}
- Cải tiến lần sau / Improve: {{ c.improvement_notes }}
{% endif %}
- Evidence sessions: {{ c.evidence.session_ids | join(", ") }}
- Risk flags: {{ c.risk_flags | join(", ") if c.risk_flags else "none" }}

{% endfor %}
{% else %}
_No candidates passed critique._
{% endif %}

## Rejected candidates

{% if rejected %}
{% for c in rejected %}
- `{{ c.name }}` — {{ c.rejected_reason }}
{% endfor %}
{% else %}
_None._
{% endif %}
""")


def render_pattern_report(
    *,
    date: str,
    date_range: str,
    sessions_scanned: int,
    clusters: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str:
    accepted = [c for c in candidates if not c.get("rejected_reason")]
    rejected = [c for c in candidates if c.get("rejected_reason")]
    for c in accepted:
        score = c.get("final_score") or c.get("prelim_score") or c.get("score") or {}
        c["_score_total"] = sum(score.values())
    return _PATTERN_REPORT_TMPL.render(
        date=date,
        date_range=date_range,
        sessions_scanned=sessions_scanned,
        clusters=clusters,
        candidates=candidates,
        accepted=accepted,
        rejected=rejected,
    )


from pathlib import Path

from jinja2 import FileSystemLoader


_TEMPLATES_DIR = Path(__file__).parent / "synth_templates"
_file_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_skill_dir(
    *,
    candidate: dict[str, Any],
    filled: dict[str, Any],
    output_dir: Path,
    generated_on: str,
) -> Path:
    """Render Path B fallback skill folder: SKILL.md + golden_tests.md.

    `candidate` is one element from candidate_skills.json; `filled` is the LLM
    template-fill output (steps + 3 golden tests).
    """
    skill_dir = output_dir / candidate["name"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "name": candidate["name"],
        "trigger_vi": candidate["trigger_intent"]["vi"],
        "trigger_en": candidate["trigger_intent"]["en"],
        "behavior_class": candidate.get("behavior_class", "process"),
        "risk_flags": candidate.get("risk_flags") or [],
        "evidence_session_ids": candidate.get("evidence", {}).get("session_ids", []),
        "generated_on": generated_on,
        "steps_markdown": filled["steps_markdown"],
        "golden_test_1": filled["golden_test_1"],
        "golden_test_2": filled["golden_test_2"],
        "golden_test_3": filled["golden_test_3"],
    }
    (skill_dir / "SKILL.md").write_text(
        _file_env.get_template("SKILL.md.j2").render(**ctx), encoding="utf-8"
    )
    (skill_dir / "golden_tests.md").write_text(
        _file_env.get_template("golden_tests.md.j2").render(**ctx), encoding="utf-8"
    )
    return skill_dir
