"""Lượt 2 — LLM-as-judge: aggregate sessions → cluster → call Claude → candidates.

Usage:
    python scripts/judge.py \\
        --sessions-dir data/sessions_2026-06-13_runAt_<runTs> \\
        [--installed-skills-dir ~/.claude/skills] \\
        [--top-candidates 5]

Outputs to data/judge_<date>/{cluster_summary.json, pattern_report.md,
candidate_skills.json, _raw_judge_output.txt}.
"""

from __future__ import annotations

import json
import sys
from datetime import date as _date
from pathlib import Path

import click

# Allow `from _lib.* import ...` when run as `python scripts/judge.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.aggregator import aggregate, load_sessions  # noqa: E402
from _lib.candidate_schema import (  # noqa: E402
    apply_recurrence_guard,
    normalize_skill_type,
    split_accepted,
)
from _lib.claude_runner import run_claude_json  # noqa: E402
from _lib.judge_prompts import build_deepdive_prompt, build_triage_prompt  # noqa: E402
from _lib.render_proposal import render_pattern_report  # noqa: E402
from _lib.trace_loader import load_traces  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"


def _list_installed_skills(skills_dir: Path) -> list[str]:
    if not skills_dir.exists():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if p.is_dir())


@click.command()
@click.option(
    "--sessions-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory of session JSONL produced by scan.py",
)
@click.option(
    "--installed-skills-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "skills",
    show_default=True,
)
@click.option("--top-candidates", type=int, default=5, show_default=True)
@click.option("--min-recurrence", type=int, default=2, show_default=True,
              help="Reject candidates whose evidence spans fewer sessions.")
@click.option("--max-deepdive", type=int, default=5, show_default=True,
              help="Cap how many triaged candidates get a deep-dive LLM call.")
@click.option("--timeout", type=float, default=180.0, show_default=True)
def main(
    sessions_dir: Path,
    installed_skills_dir: Path,
    top_candidates: int,
    min_recurrence: int,
    max_deepdive: int,
    timeout: float,
) -> None:
    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"judge_{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"[judge] loading sessions from {sessions_dir}")
    sessions = load_sessions(sessions_dir)
    click.echo(f"[judge] loaded {len(sessions)} sessions")

    clusters = aggregate(sessions)
    cluster_dicts = [c.to_dict() for c in clusters]
    (out_dir / "cluster_summary.json").write_text(
        json.dumps(cluster_dicts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    click.echo(f"[judge] {len(clusters)} tool-usage group(s)")

    if not clusters:
        click.echo("[judge] no sessions → skipping LLM judge")
        final: list[dict] = []
        accepted: list[dict] = []
    else:
        installed = _list_installed_skills(installed_skills_dir)

        # ── PASS 1: triage on summaries ──────────────────────────────────────
        click.echo(f"[judge] triage: `claude -p` (timeout={timeout}s)")
        triage_prompt = build_triage_prompt(cluster_dicts, installed)
        triage = run_claude_json(triage_prompt, timeout=timeout)
        (out_dir / "_raw_triage.txt").write_text(
            json.dumps(triage, ensure_ascii=False, indent=2), encoding="utf-8")
        triage = [normalize_skill_type(c) for c in triage]

        # ── GUARD: code-level recurrence check ───────────────────────────────
        triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
        accepted_triage, rejected = split_accepted(triage)
        click.echo(
            f"[judge] triage: {len(accepted_triage)} pass, {len(rejected)} rejected"
        )
        accepted_triage = accepted_triage[:max_deepdive]

        # ── PASS 2: deep-dive over full ordered traces ───────────────────────
        enriched: list[dict] = []
        for c in accepted_triage:
            src = c.get("evidence", {}).get("source_files", [])
            traces = load_traces(src, sessions_dir)
            click.echo(f"[judge] deep-dive: {c['name']} ({len(traces)} traces)")
            dd = run_claude_json(build_deepdive_prompt(c, traces), timeout=timeout)
            (out_dir / f"_raw_deepdive_{c['name']}.txt").write_text(
                json.dumps(dd, ensure_ascii=False, indent=2), encoding="utf-8")
            enriched.append({**c, **dd})

        accepted = [c for c in enriched if not c.get("rejected_reason")]
        accepted = sorted(
            accepted,
            key=lambda c: sum(c.get("final_score", c.get("prelim_score", {})).values()),
            reverse=True,
        )[:top_candidates]
        rejected += [c for c in enriched if c.get("rejected_reason")]
        final = accepted + rejected

    (out_dir / "candidate_skills.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_md = render_pattern_report(
        date=today,
        date_range=str(sessions_dir.name),
        sessions_scanned=len(sessions),
        clusters=cluster_dicts,
        candidates=final,
    )
    (out_dir / "pattern_report.md").write_text(report_md, encoding="utf-8")

    click.echo(
        f"[judge] done. {len(accepted)} accepted, "
        f"{len(final) - len(accepted)} rejected → {out_dir}"
    )


if __name__ == "__main__":
    main()
