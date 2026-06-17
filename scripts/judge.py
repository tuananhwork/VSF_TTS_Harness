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

from _lib.aggregator import (  # noqa: E402
    aggregate,
    load_sessions,
    recompute_candidate_metrics,
)
from _lib.candidate_schema import (  # noqa: E402
    apply_recurrence_guard,
    normalize_skill_name,
    normalize_skill_type,
    split_accepted,
)
from functools import partial  # noqa: E402

from _lib.claude_runner import (  # noqa: E402
    CancelToken,
    ClaudeRunError,
    provider_label,
    run_claude_json,
)
from _lib.debate import run_debate  # noqa: E402
from _lib.judge_prompts import (  # noqa: E402
    JUDGES,
    build_consolidator_prompt,
    build_extract_prompt,
    build_triage_prompt,
)
from _lib.render_proposal import render_pattern_report  # noqa: E402
from _lib.trace_loader import load_traces  # noqa: E402


def _get_data_root() -> Path:
    import sys as _sys
    if getattr(_sys, "frozen", False):
        return Path(_sys.executable).parent / "pattern_data"
    return Path(__file__).resolve().parent.parent / "data"


DATA_ROOT = _get_data_root()


def _list_installed_skills(skills_dir: Path) -> list[str]:
    if not skills_dir.exists():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if p.is_dir())


def run_judge(
    sessions_dir: Path,
    min_recurrence: int = 2,
    max_deepdive: int = 5,
    top_candidates: int = 5,
    timeout: float = 300.0,
    installed_skills_dir: Path | None = None,
    log_fn=print,
    cancel: CancelToken | None = None,
    status_fn=None,
) -> Path:
    """Chạy judge pipeline. Trả về Path tới candidate_skills.json.

    `cancel` (CancelToken) cho phép huỷ thật: mọi call LLM đi qua `runner` đã bind
    token, và ta kiểm tra `raise_if_cancelled()` ở các mốc để dừng ngay.
    `status_fn(text)` (tuỳ chọn) cập nhật thanh 'live' trước mỗi call LLM (UX).
    """
    if installed_skills_dir is None:
        installed_skills_dir = Path.home() / ".claude" / "skills"

    if status_fn is None:
        status_fn = lambda *_: None  # noqa: E731

    # Mọi call LLM trong judge đi qua runner này → tự huỷ được khi cancel.
    runner = partial(run_claude_json, cancel=cancel)

    def _check_cancel() -> None:
        if cancel is not None:
            cancel.raise_if_cancelled()

    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"judge_{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log_fn(f"[judge] loading sessions from {sessions_dir}")
    sessions = load_sessions(sessions_dir)
    log_fn(f"[judge] loaded {len(sessions)} sessions")

    clusters = aggregate(sessions)
    cluster_dicts = [c.to_dict() for c in clusters]
    (out_dir / "cluster_summary.json").write_text(
        json.dumps(cluster_dicts, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    log_fn(f"[judge] {len(clusters)} tool-usage group(s)")

    if not clusters:
        log_fn("[judge] no sessions → skipping LLM judge")
        final: list[dict] = []
        accepted: list[dict] = []
    else:
        installed = _list_installed_skills(installed_skills_dir)

        log_fn(f"[judge] triage: `{provider_label()}` (timeout={timeout}s)")
        status_fn(f"Triage · {len(clusters)} nhóm session")
        triage_prompt = build_triage_prompt(cluster_dicts, installed)
        triage = runner(triage_prompt, timeout=timeout)
        (out_dir / "_raw_triage.txt").write_text(
            json.dumps(triage, ensure_ascii=False, indent=2), encoding="utf-8")
        triage = [normalize_skill_name(normalize_skill_type(c)) for c in triage]
        triage = recompute_candidate_metrics(triage, sessions)
        triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
        accepted_triage, rejected = split_accepted(triage)
        log_fn(f"[judge] triage: {len(accepted_triage)} pass, {len(rejected)} rejected")
        accepted_triage = accepted_triage[:max_deepdive]

        enriched: list[dict] = []
        n_dd = len(accepted_triage)
        for i, c in enumerate(accepted_triage, 1):
            _check_cancel()  # dừng ngay trước khi tốn LLM cho candidate kế tiếp
            src = c.get("evidence", {}).get("source_files", [])
            traces = load_traces(src, sessions_dir)
            log_fn(f"[judge] debate: {c['name']} ({len(traces)} traces, {len(JUDGES)} judges)")

            try:
                status_fn(f"Trích xuất: {c['name']} ({i}/{n_dd})")
                facts = runner(build_extract_prompt(c, traces), timeout=timeout)
                (out_dir / f"_raw_extract_{c['name']}.txt").write_text(
                    json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
            except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
                log_fn(f"[judge]   ! extract failed ({e})")
                facts = {"extract_error": str(e)}

            status_fn(f"Tranh luận: {c['name']} ({i}/{n_dd})")
            verdicts = run_debate(
                c, facts, traces, judges=JUDGES, runner=runner, timeout=timeout
            )
            (out_dir / f"_raw_debate_{c['name']}.txt").write_text(
                json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")
            _check_cancel()  # debate nuốt exception nội bộ → kiểm tra lại ở đây

            try:
                status_fn(f"Tổng hợp: {c['name']} ({i}/{n_dd})")
                verdict = runner(
                    build_consolidator_prompt(c, facts, verdicts), timeout=timeout)
                (out_dir / f"_raw_consolidate_{c['name']}.txt").write_text(
                    json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
            except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
                log_fn(f"[judge]   ! consolidator failed ({e}); keeping candidate")
                verdict = {"consolidator_error": str(e)}

            enriched.append({**c, **facts, "debate": verdicts, **verdict})

        accepted = [c for c in enriched if not c.get("rejected_reason")]
        accepted = sorted(
            accepted,
            key=lambda c: sum(c.get("final_score", c.get("prelim_score", {})).values()),
            reverse=True,
        )[:top_candidates]
        rejected += [c for c in enriched if c.get("rejected_reason")]
        final = accepted + rejected

    candidates_path = out_dir / "candidate_skills.json"
    candidates_path.write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    report_md = render_pattern_report(
        date=today,
        date_range=str(sessions_dir.name),
        sessions_scanned=len(sessions),
        clusters=cluster_dicts,
        candidates=final,
    )
    (out_dir / "pattern_report.md").write_text(report_md, encoding="utf-8")
    log_fn(f"[judge] done. {len(accepted)} accepted, {len(final) - len(accepted)} rejected → {out_dir}")
    return candidates_path


@click.command()
@click.option("--sessions-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--installed-skills-dir", type=click.Path(file_okay=False, path_type=Path), default=Path.home() / ".claude" / "skills")
@click.option("--top-candidates", type=int, default=5)
@click.option("--min-recurrence", type=int, default=2)
@click.option("--max-deepdive", type=int, default=5)
@click.option("--timeout", type=float, default=300.0)
def main(
    sessions_dir: Path,
    installed_skills_dir: Path,
    top_candidates: int,
    min_recurrence: int,
    max_deepdive: int,
    timeout: float,
) -> None:
    run_judge(
        sessions_dir=sessions_dir,
        min_recurrence=min_recurrence,
        max_deepdive=max_deepdive,
        top_candidates=top_candidates,
        timeout=timeout,
        installed_skills_dir=installed_skills_dir,
    )


if __name__ == "__main__":
    main()
