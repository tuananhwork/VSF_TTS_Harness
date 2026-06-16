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
            "repeat_rate": 0.0,
            "failure_rate": 0.0,
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
            "metrics": {"recurrence": 3, "repeat_rate": 0.0, "failure_rate": 0.0,
                        "behavior_class": "process"},
            "final_score": {"recurrence": 4, "cohesion": 4, "personalization": 3},
            "behavior_class": "inefficient",
            "good_points": ["đọc file trước khi tóm tắt"],
            "weak_points": ["phải làm lại 3 lần vì thiếu ngữ cảnh"],
            "improvement_notes": "lần sau hỏi rõ độ dài mong muốn trước",
            "risk_flags": [],
            "rejected_reason": None,
            "debate": [
                {"judge": "efficiency", "stance": "approve", "axis_score": 5,
                 "argument": "tốn 12 lượt chat lặp lại"},
                {"judge": "quality", "stance": "approve", "axis_score": 4,
                 "argument": "user phải sửa sai 4 lần"},
            ],
            "consolidator_note": "Phê duyệt: flow lặp lại, đáng đóng gói",
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
    # Cách B: debate verdicts + consolidator note surfaced for the human reviewer.
    assert "efficiency" in md and "quality" in md
    assert "tốn 12 lượt chat lặp lại" in md
    assert "Phê duyệt: flow lặp lại, đáng đóng gói" in md
    # Recomputed metrics surfaced so the human sees the authoritative recurrence.
    assert "recurrence (recomputed): 3" in md
    # ...and the metric line must end with a newline (not glue onto "Score total").
    assert "failure_rate: 0.000\n" in md
