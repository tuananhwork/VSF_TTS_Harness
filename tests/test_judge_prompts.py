"""Tests for scripts/_lib/judge_prompts.py (V2 two-pass prompts)."""

from __future__ import annotations

from _lib.judge_prompts import (
    JUDGES,
    build_consolidator_prompt,
    build_extract_prompt,
    build_judge_prompt,
    build_triage_prompt,
)


def _group() -> dict:
    return {
        "session_ids": ["s1", "s2"],
        "source_files": ["a.jsonl", "b.jsonl"],
        "intent_seeds": ["Tóm tắt file", "đọc và tóm tắt file"],
        "tool_sequence_per_session": [["Read", "Edit×2"], ["Read", "Edit"]],
        "repeat_rate": 0.0,
        "failure_rate": 0.0,
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


def _candidate() -> dict:
    return {
        "name": "summarize_file",
        "skill_type": "improvement_lesson",
        "trigger_intent": {"vi": "Tóm tắt file", "en": "Summarize file"},
    }


def _traces() -> dict:
    return {
        "sid-a": [
            {"role": "user", "text": "Tóm tắt file", "feedback": None},
            {"role": "assistant", "tools": ["Read", "Edit×2"], "feedback": None},
            {"role": "assistant", "tools": ["bash"], "feedback": "repeat"},
        ],
    }


def test_extract_prompt_requests_factual_fields_only() -> None:
    prompt = build_extract_prompt(_candidate(), _traces())
    assert "summarize_file" in prompt
    assert "repeat" in prompt                 # trace markers surfaced
    assert "action_template" in prompt       # ordered flow requested
    assert "weak_points" in prompt
    assert "improvement_notes" in prompt
    assert "golden_tests" in prompt
    # Extract is neutral: it does NOT score or reject — that's the consolidator's job.
    assert "final_score" not in prompt
    assert "rejected_reason" not in prompt


def test_judges_list_has_active_mvp_pair() -> None:
    ids = [j["id"] for j in JUDGES]
    assert ids == ["efficiency", "quality"]


def test_judge_prompt_carries_axis_candidate_and_facts() -> None:
    facts = {"action_template": [{"step": 1, "tool": "Read", "input_shape": "path"}]}
    for judge in JUDGES:
        prompt = build_judge_prompt(judge, _candidate(), facts, _traces())
        assert judge["label_vi"] in prompt       # judge persona injected
        assert "summarize_file" in prompt          # candidate under debate
        assert "axis_score" in prompt              # judge scores its own axis
        assert "stance" in prompt
        assert "argument" in prompt


def test_consolidator_prompt_includes_all_verdicts() -> None:
    facts = {"action_template": []}
    verdicts = [
        {"judge": "efficiency", "stance": "approve", "axis_score": 5,
         "argument": "12 lượt chat lặp lại"},
        {"judge": "quality", "stance": "approve", "axis_score": 4,
         "argument": "sửa sai 4 lần"},
    ]
    prompt = build_consolidator_prompt(_candidate(), facts, verdicts)
    assert "efficiency" in prompt and "quality" in prompt
    assert "12 lượt chat lặp lại" in prompt
    assert "final_score" in prompt
    assert "rejected_reason" in prompt
    assert "consolidator_note" in prompt


def test_consolidator_prompt_marks_metrics_authoritative() -> None:
    cand = {"name": "x", "metrics": {"recurrence": 3, "repeat_rate": 0.0,
                                     "failure_rate": 0.0, "behavior_class": "process"}}
    prompt = build_consolidator_prompt(cand, {}, [])
    assert "candidate.metrics" in prompt      # hướng dẫn dùng số thật
    assert '"recurrence": 3' in prompt          # số thật được serialize vào prompt
