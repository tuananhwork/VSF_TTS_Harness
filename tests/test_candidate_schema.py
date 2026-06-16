"""Tests for scripts/_lib/candidate_schema.py."""

from __future__ import annotations

import pytest

from _lib.candidate_schema import (
    apply_recurrence_guard,
    normalize_skill_name,
    normalize_skill_type,
    slugify_skill_name,
    split_accepted,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("summarize_pdf", "summarize-pdf"),       # snake_case -> kebab
        ("Summarize PDF", "summarize-pdf"),        # caps + space
        ("clean__data--export", "clean-data-export"),  # consecutive separators
        ("-leading-and-trailing-", "leading-and-trailing"),
        ("tóm_tắt_pdf!!!", "t-m-t-t-pdf"),         # non-ascii/punct -> hyphen
        ("", "unnamed-skill"),                      # empty fallback
        ("___", "unnamed-skill"),                   # all-separator fallback
    ],
)
def test_slugify_skill_name(raw: str, expected: str) -> None:
    assert slugify_skill_name(raw) == expected


def test_slugify_skill_name_is_idempotent() -> None:
    once = slugify_skill_name("Some Messy_Name")
    assert slugify_skill_name(once) == once


def test_slugify_skill_name_caps_length_without_trailing_hyphen() -> None:
    out = slugify_skill_name("a-" * 50, max_len=64)
    assert len(out) <= 64
    assert not out.endswith("-")


def test_normalize_skill_name_does_not_mutate_input() -> None:
    c = {"name": "summarize_pdf"}
    out = normalize_skill_name(c)
    assert out["name"] == "summarize-pdf"
    assert c["name"] == "summarize_pdf"


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


def test_recurrence_guard_prefers_verified_metrics_recurrence() -> None:
    # Candidate cites 3 ids but only 1 was real → metrics.recurrence == 1 → reject.
    cands = [{
        "name": "a",
        "evidence": {"session_ids": ["s1", "s2", "s3"]},
        "metrics": {"recurrence": 1},
    }]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0]["rejected_reason"] == "low_recurrence"


def test_recurrence_guard_accepts_when_verified_recurrence_meets_min() -> None:
    cands = [{
        "name": "a",
        "evidence": {"session_ids": ["s1", "s2"]},
        "metrics": {"recurrence": 2},
    }]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0].get("rejected_reason") is None


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
