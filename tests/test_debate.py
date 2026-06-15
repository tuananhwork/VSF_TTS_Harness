"""Tests for scripts/_lib/debate.py — parallel multi-judge orchestration."""

from __future__ import annotations

from _lib.debate import run_debate


def _judges() -> list[dict]:
    return [
        {"id": "efficiency", "label_vi": "Năng suất", "label_en": "Efficiency",
         "persona": "..."},
        {"id": "quality", "label_vi": "Chất lượng", "label_en": "Quality",
         "persona": "..."},
    ]


def test_run_debate_collects_one_verdict_per_judge() -> None:
    candidate = {"name": "x"}
    facts = {"action_template": []}

    def fake_runner(prompt: str, *, timeout: float) -> dict:
        # Echo a verdict; judge id is embedded in the prompt by build_judge_prompt.
        return {"stance": "approve", "axis_score": 4, "argument": "ok"}

    verdicts = run_debate(
        candidate, facts, {}, judges=_judges(), runner=fake_runner, timeout=10.0
    )
    assert len(verdicts) == 2
    assert {v["judge"] for v in verdicts} == {"efficiency", "quality"}
    assert all(v["stance"] == "approve" for v in verdicts)


def test_run_debate_tolerates_single_judge_failure() -> None:
    candidate = {"name": "x"}

    def flaky_runner(prompt: str, *, timeout: float) -> dict:
        if "Chất lượng" in prompt:
            raise RuntimeError("judge timed out")
        return {"stance": "approve", "axis_score": 5, "argument": "ok"}

    verdicts = run_debate(
        candidate, {}, {}, judges=_judges(), runner=flaky_runner, timeout=10.0
    )
    by_id = {v["judge"]: v for v in verdicts}
    assert by_id["efficiency"]["stance"] == "approve"
    # Failed judge still appears so the consolidator sees the gap, with an error marker.
    assert by_id["quality"].get("error")
    assert "judge timed out" in by_id["quality"]["error"]
