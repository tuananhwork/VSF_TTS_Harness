"""Tests for scripts/_lib/judge_prompts.py (V2 two-pass prompts)."""

from __future__ import annotations

from _lib.judge_prompts import build_deepdive_prompt, build_triage_prompt


def _group() -> dict:
    return {
        "session_ids": ["s1", "s2"],
        "source_files": ["a.jsonl", "b.jsonl"],
        "intent_seeds": ["Tóm tắt file", "đọc và tóm tắt file"],
        "tool_sequence_per_session": [["Read", "Edit×2"], ["Read", "Edit"]],
        "retry_rate": 0.0,
        "behavior_class_hint": "process",
    }


def test_triage_prompt_includes_sequence_and_intent_and_skill_type() -> None:
    prompt = build_triage_prompt([_group()], ["existing_skill"])
    assert "tool_sequence_per_session" in prompt
    assert "intent_seeds" in prompt
    assert "skill_type" in prompt
    assert "existing_skill" in prompt
    # Triage stays light — no deep-dive-only fields leak into this prompt.
    assert "golden_tests" not in prompt
    assert "action_template" not in prompt


def test_triage_prompt_names_both_skill_types() -> None:
    prompt = build_triage_prompt([_group()], [])
    assert "process_macro" in prompt
    assert "improvement_lesson" in prompt


def test_deepdive_prompt_includes_trace_and_ordered_schema() -> None:
    candidate = {
        "name": "summarize_file",
        "skill_type": "improvement_lesson",
        "trigger_intent": {"vi": "Tóm tắt file", "en": "Summarize file"},
    }
    traces = {
        "sid-a": [
            {"role": "user", "text": "Tóm tắt file", "feedback": None},
            {"role": "assistant", "tools": ["Read", "Edit×2"], "feedback": None},
            {"role": "user", "text": "sai rồi", "feedback": "correction"},
        ],
    }
    prompt = build_deepdive_prompt(candidate, traces)
    assert "summarize_file" in prompt
    assert "correction" in prompt          # trace markers surfaced
    assert "action_template" in prompt      # ordered flow requested
    assert "weak_points" in prompt
    assert "improvement_notes" in prompt
    assert "golden_tests" in prompt
