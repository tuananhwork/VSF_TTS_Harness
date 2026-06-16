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
