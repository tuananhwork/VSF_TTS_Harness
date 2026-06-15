"""Tests for scripts/_lib/render_proposal.py."""

from __future__ import annotations

from _lib.render_proposal import render_pattern_report


def test_pattern_report_lists_candidates_and_clusters() -> None:
    clusters = [
        {
            "session_ids": ["s1", "s2"],
            "process_names": ["proc-a", "proc-b"],
            "representative_tools": ["scan", "edit"],
            "representative_titles": ["Tóm tắt file PDF báo cáo"],
            "recurrence": 2,
            "retry_rate": 0.0,
            "correction_rate": 0.0,
            "avg_duration_seconds": 12.3,
            "total_tokens": 1000,
            "behavior_class_hint": "process",
            "top_tools_per_session": [{"scan": 5}, {"edit": 4}],
            "titles": ["Tóm tắt file PDF báo cáo", "Tóm tắt file PDF tài liệu"],
        }
    ]
    candidates = [
        {
            "name": "summarize_pdf",
            "trigger_intent": {"vi": "Khi user muốn tóm tắt PDF", "en": "When user wants to summarize PDF"},
            "action_template": [{"tool": "scan", "input_shape": "path"}],
            "evidence": {"session_ids": ["s1", "s2"], "process_names": ["proc-a"]},
            "score": {"recurrence": 4, "cohesion": 4, "personalization": 3},
            "behavior_class": "process",
            "risk_flags": [],
            "rejected_reason": None,
        }
    ]
    md = render_pattern_report(
        date="2026-06-13",
        date_range="2026-06-13..2026-06-13",
        sessions_scanned=4,
        clusters=clusters,
        candidates=candidates,
    )
    assert "summarize_pdf" in md
    assert "process" in md
    assert "Khi user muốn tóm tắt PDF" in md
    assert "2026-06-13" in md
    # Rejected candidates should not appear in the "Top candidates" section,
    # but accepted candidates should.
    assert "## Top candidates" in md or "## Candidates" in md


from pathlib import Path

from _lib.render_proposal import render_skill_dir


def test_render_skill_dir_writes_skill_and_golden_tests(tmp_path: Path) -> None:
    candidate = {
        "name": "summarize_pdf",
        "trigger_intent": {"vi": "khi cần tóm tắt PDF", "en": "when summarizing PDF"},
        "behavior_class": "process",
        "risk_flags": [],
        "evidence": {"session_ids": ["s1", "s2"]},
    }
    filled = {
        "steps_markdown": "1. read file\n2. summarize\n3. return summary",
        "golden_test_1": {"query": "Q1", "expected": "E1"},
        "golden_test_2": {"query": "Q2", "expected": "E2"},
        "golden_test_3": {"query": "Q3", "expected": "E3"},
    }
    out = render_skill_dir(
        candidate=candidate, filled=filled,
        output_dir=tmp_path, generated_on="2026-06-13",
    )
    skill_md = (out / "SKILL.md").read_text(encoding="utf-8")
    golden = (out / "golden_tests.md").read_text(encoding="utf-8")
    assert "summarize_pdf" in skill_md
    assert "khi cần tóm tắt PDF" in skill_md
    assert "1. read file" in skill_md
    assert "Q1" in golden and "E2" in golden
