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
- titles: {{ cl.titles | join(" | ") }}
- sessions: {{ cl.process_names | join(", ") }}

{% endfor %}

## Top candidates (passed critique)

{% if accepted %}
{% for c in accepted %}
### {{ loop.index }}. `{{ c.name }}` — {{ c.behavior_class }}
- Trigger (VI): {{ c.trigger_intent.vi }}
- Trigger (EN): {{ c.trigger_intent.en }}
- Score: recurrence={{ c.score.recurrence }}, cohesion={{ c.score.cohesion }}, personalization={{ c.score.personalization }} (total {{ c.score.recurrence + c.score.cohesion + c.score.personalization }})
- Action template:
{% for step in c.action_template %}
  - `{{ step.tool }}` ← {{ step.input_shape }}
{% endfor %}
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
    return _PATTERN_REPORT_TMPL.render(
        date=date,
        date_range=date_range,
        sessions_scanned=sessions_scanned,
        clusters=clusters,
        candidates=candidates,
        accepted=accepted,
        rejected=rejected,
    )
