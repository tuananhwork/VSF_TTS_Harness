"""Tests for scripts/_lib/candidate_schema.py."""

from __future__ import annotations

from _lib.candidate_schema import (
    apply_recurrence_guard,
    normalize_skill_type,
    split_accepted,
)


def test_recurrence_guard_rejects_singleton_evidence() -> None:
    cands = [
        {"name": "a", "evidence": {"session_ids": ["s1", "s2"]}},
        {"name": "b", "evidence": {"session_ids": ["s1"]}},
    ]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    by_name = {c["name"]: c for c in out}
    assert by_name["a"].get("rejected_reason") is None
    assert by_name["b"]["rejected_reason"] == "low_recurrence"


def test_recurrence_guard_counts_distinct_sessions() -> None:
    cands = [{"name": "a", "evidence": {"session_ids": ["s1", "s1"]}}]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0]["rejected_reason"] == "low_recurrence"


def test_recurrence_guard_preserves_existing_rejection() -> None:
    cands = [{"name": "a", "evidence": {"session_ids": ["s1"]},
              "rejected_reason": "too_generic"}]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0]["rejected_reason"] == "too_generic"


def test_recurrence_guard_does_not_mutate_input() -> None:
    cands = [{"name": "b", "evidence": {"session_ids": ["s1"]}}]
    apply_recurrence_guard(cands, min_recurrence=2)
    assert "rejected_reason" not in cands[0]


def test_normalize_skill_type_infers_from_behavior_class() -> None:
    assert normalize_skill_type(
        {"behavior_class": "inefficient"})["skill_type"] == "improvement_lesson"
    assert normalize_skill_type(
        {"behavior_class": "process"})["skill_type"] == "process_macro"


def test_normalize_skill_type_keeps_explicit_value() -> None:
    c = {"behavior_class": "process", "skill_type": "improvement_lesson"}
    assert normalize_skill_type(c)["skill_type"] == "improvement_lesson"


def test_split_accepted_partitions_by_rejected_reason() -> None:
    cands = [
        {"name": "a"},
        {"name": "b", "rejected_reason": "low_recurrence"},
        {"name": "c", "rejected_reason": None},
    ]
    accepted, rejected = split_accepted(cands)
    assert [c["name"] for c in accepted] == ["a", "c"]
    assert [c["name"] for c in rejected] == ["b"]
