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
from _lib.claude_runner import ClaudeRunError, run_claude, run_claude_json  # noqa: E402
from _lib.judge_prompts import build_judge_prompt  # noqa: E402
from _lib.render_proposal import render_pattern_report  # noqa: E402


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
@click.option("--timeout", type=float, default=180.0, show_default=True)
def main(
    sessions_dir: Path,
    installed_skills_dir: Path,
    top_candidates: int,
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
        candidates: list[dict] = []
    else:
        installed = _list_installed_skills(installed_skills_dir)
        prompt = build_judge_prompt(cluster_dicts, installed)
        click.echo(f"[judge] calling `claude -p` (timeout={timeout}s)")
        try:
            raw = run_claude(prompt, timeout=timeout)
            (out_dir / "_raw_judge_output.txt").write_text(raw, encoding="utf-8")
            from _lib.claude_runner import extract_json_block
            candidates = json.loads(extract_json_block(raw))
            if not isinstance(candidates, list):
                raise ValueError("expected JSON array at top level")
        except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
            click.echo(f"[judge] first parse failed: {e}; retrying via self-heal")
            candidates = run_claude_json(prompt, timeout=timeout)

    accepted = [c for c in candidates if not c.get("rejected_reason")]
    accepted = sorted(
        accepted,
        key=lambda c: sum(c.get("score", {}).values()),
        reverse=True,
    )[:top_candidates]
    final = accepted + [c for c in candidates if c.get("rejected_reason")]
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
