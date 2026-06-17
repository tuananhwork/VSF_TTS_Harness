"""Cách B debate: run each judge over the same facts+traces in parallel, then
collect their verdicts for the consolidator.

`run_claude_json` is synchronous and `ccs <profile> -p` is subprocess I/O-bound, so a
thread pool is enough — no async needed. A single judge timing out must not tank
the candidate: its failure is recorded as a verdict with an `error` field so the
consolidator still sees the gap.

See docs/products/agent-debate.md "Quyết định kiến trúc — Cách B".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from _lib.judge_prompts import build_judge_prompt

Runner = Callable[..., Any]


def _run_one(
    judge: dict[str, str],
    candidate: dict[str, Any],
    facts: dict[str, Any],
    traces: dict[str, list[dict[str, Any]]],
    runner: Runner,
    timeout: float,
) -> dict[str, Any]:
    prompt = build_judge_prompt(judge, candidate, facts, traces)
    try:
        verdict = runner(prompt, timeout=timeout)
        return {"judge": judge["id"], **verdict}
    except Exception as e:  # judge-local failure must not abort the debate
        return {"judge": judge["id"], "error": str(e)}


def run_debate(
    candidate: dict[str, Any],
    facts: dict[str, Any],
    traces: dict[str, list[dict[str, Any]]],
    *,
    judges: list[dict[str, str]],
    runner: Runner,
    timeout: float,
) -> list[dict[str, Any]]:
    """Call every judge in parallel; return one verdict dict per judge, in the
    same order as `judges`. Each verdict is tagged with the judge id; a failed
    judge yields {"judge": id, "error": ...}."""
    with ThreadPoolExecutor(max_workers=max(1, len(judges))) as pool:
        futures = [
            pool.submit(_run_one, j, candidate, facts, traces, runner, timeout)
            for j in judges
        ]
        return [f.result() for f in futures]
