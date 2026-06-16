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
- recurrence: {{ cl.recurrence }}, repeat_rate: {{ cl.repeat_rate }}, failure_rate: {{ cl.failure_rate }}
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
{% if c.metrics %}
- recurrence (recomputed): {{ c.metrics.recurrence }}, repeat_rate: {{ "%.3f"|format(c.metrics.repeat_rate) }}, failure_rate: {{ "%.3f"|format(c.metrics.failure_rate) }}{{ (" — ⚠️ bỏ %d session_id bịa" % (c.metrics.unknown_session_ids | length)) if c.metrics.unknown_session_ids else "" }}
{% endif %}
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
{% if c.debate %}
- Debate (judge verdicts):
{% for v in c.debate %}
  - **{{ v.judge }}** [{{ v.stance }}{% if v.axis_score is not none %}, {{ v.axis_score }}/5{% endif %}]: {{ v.argument or v.error }}
{% endfor %}
{% endif %}
{% if c.consolidator_note %}
- Consolidator: {{ c.consolidator_note }}
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
