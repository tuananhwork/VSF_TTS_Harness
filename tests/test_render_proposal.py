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
            "skill_type": "improvement_lesson",
            "trigger_intent": {"vi": "Khi user muốn tóm tắt PDF", "en": "When user wants to summarize PDF"},
            "action_template": [{"step": 1, "tool": "scan", "input_shape": "path"}],
            "evidence": {"session_ids": ["s1", "s2"], "process_names": ["proc-a"]},
            "final_score": {"recurrence": 4, "cohesion": 4, "personalization": 3},
            "behavior_class": "inefficient",
            "good_points": ["đọc file trước khi tóm tắt"],
            "weak_points": ["phải làm lại 3 lần vì thiếu ngữ cảnh"],
            "improvement_notes": "lần sau hỏi rõ độ dài mong muốn trước",
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
    assert "improvement_lesson" in md
    assert "Khi user muốn tóm tắt PDF" in md
    assert "2026-06-13" in md
    # V2 good/weak/improvement surfaced for learning.
    assert "phải làm lại 3 lần vì thiếu ngữ cảnh" in md
    assert "lần sau hỏi rõ độ dài mong muốn trước" in md
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


def test_render_skill_dir_improvement_lesson_surfaces_weak_and_improve(tmp_path: Path) -> None:
    candidate = {
        "name": "summarize_better",
        "skill_type": "improvement_lesson",
        "trigger_intent": {"vi": "tóm tắt file", "en": "summarize file"},
        "behavior_class": "inefficient",
        "risk_flags": [],
        "evidence": {"session_ids": ["s1", "s2"]},
        "weak_points": ["phải làm lại vì thiếu ngữ cảnh"],
        "improvement_notes": "hỏi rõ độ dài mong muốn trước khi tóm tắt",
    }
    filled = {
        "steps_markdown": "1. read\n2. summarize",
        "golden_test_1": {"query": "Q1", "expected": "E1"},
        "golden_test_2": {"query": "Q2", "expected": "E2"},
        "golden_test_3": {"query": "Q3", "expected": "E3"},
    }
    out = render_skill_dir(
        candidate=candidate, filled=filled,
        output_dir=tmp_path, generated_on="2026-06-15",
    )
    skill_md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "improvement_lesson" in skill_md
    assert "phải làm lại vì thiếu ngữ cảnh" in skill_md
    assert "hỏi rõ độ dài mong muốn trước khi tóm tắt" in skill_md


def test_render_skill_dir_process_macro_renders_ordered_flow(tmp_path: Path) -> None:
    candidate = {
        "name": "scan_edit_flow",
        "skill_type": "process_macro",
        "trigger_intent": {"vi": "quét rồi sửa", "en": "scan then edit"},
        "behavior_class": "process",
        "risk_flags": [],
        "evidence": {"session_ids": ["s1", "s2"]},
        "action_template": [
            {"step": 1, "tool": "Read", "input_shape": "path"},
            {"step": 2, "tool": "Edit", "input_shape": "diff"},
        ],
    }
    filled = {
        "steps_markdown": "fallback steps",
        "golden_test_1": {"query": "Q1", "expected": "E1"},
        "golden_test_2": {"query": "Q2", "expected": "E2"},
        "golden_test_3": {"query": "Q3", "expected": "E3"},
    }
    out = render_skill_dir(
        candidate=candidate, filled=filled,
        output_dir=tmp_path, generated_on="2026-06-15",
    )
    skill_md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "process_macro" in skill_md
    assert "`Read`" in skill_md and "`Edit`" in skill_md
