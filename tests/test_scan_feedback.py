"""Tests for scan.py structural feedback signals (repeat + pivot).

These replace the old keyword-based correction/confirm detection: the signals
are now derived from turn/action structure, not Vietnamese phrase lists.
"""

from __future__ import annotations

import json
from pathlib import Path

import scan


def _assistant_event(uuid: str, ts: str, tool_names: list[str]) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": ts,
        "message": {
            "content": [
                {"type": "tool_use", "name": name, "id": f"{uuid}-{i}", "input": {}}
                for i, name in enumerate(tool_names)
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }


def _user_event(uuid: str, ts: str, text: str) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _write_audit(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _parse(tmp_path: Path, events: list[dict]):
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, events)
    meta = tmp_path / "local_test.json"
    meta.write_text("{}", encoding="utf-8")
    return scan.parse_session(meta, audit, "ws1")


# ── repeat ────────────────────────────────────────────────────────────────────


def test_repeat_flags_same_tool_in_later_turn_within_window(tmp_path: Path) -> None:
    summary, turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Bash"]),
        _assistant_event("a2", "2026-06-15T10:00:10", ["Bash"]),
    ])
    assert summary.repeat_count == 1
    assert [t.feedback_flag for t in turns] == [None, "repeat"]


def test_repeat_not_flagged_outside_window(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Bash"]),
        _assistant_event("a2", "2026-06-15T10:02:00", ["Bash"]),  # 120s later
    ])
    assert summary.repeat_count == 0


def test_repeat_ignores_intra_turn_duplicate_tools(tmp_path: Path) -> None:
    # A single turn editing several files is normal batching, not a redo.
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Edit", "Edit", "Edit"]),
    ])
    assert summary.repeat_count == 0


# ── pivot ─────────────────────────────────────────────────────────────────────


def test_pivot_flags_user_turn_that_changes_tool_direction(tmp_path: Path) -> None:
    # Assistant was reading; user speaks; assistant switches to a totally
    # different toolset → the plan pivoted.
    summary, turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Read", "Grep"]),
        _user_event("u1", "2026-06-15T10:00:05", "đổi hướng giúp mình"),
        _assistant_event("a2", "2026-06-15T10:00:10", ["WebSearch", "WebFetch"]),
    ])
    assert summary.pivot_count == 1
    user_turn = next(t for t in turns if t.role == "user")
    assert user_turn.feedback_flag == "pivot"


def test_no_pivot_when_assistant_continues_same_tools(tmp_path: Path) -> None:
    summary, turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Read"]),
        _user_event("u1", "2026-06-15T10:00:05", "ok tiếp tục"),
        _assistant_event("a2", "2026-06-15T10:00:10", ["Read"]),
    ])
    assert summary.pivot_count == 0
    user_turn = next(t for t in turns if t.role == "user")
    assert user_turn.feedback_flag is None


def test_no_pivot_when_no_actions_follow_user_turn(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Read"]),
        _user_event("u1", "2026-06-15T10:00:05", "cảm ơn nhé"),
    ])
    assert summary.pivot_count == 0


def test_no_pivot_for_opening_user_instruction(tmp_path: Path) -> None:
    # First user turn has no prior assistant flow to pivot from.
    summary, _turns, _ = _parse(tmp_path, [
        _user_event("u1", "2026-06-15T10:00:00", "tạo slide sản phẩm X"),
        _assistant_event("a1", "2026-06-15T10:00:10", ["Read", "Edit"]),
    ])
    assert summary.pivot_count == 0


def test_correction_keyword_alone_does_not_flag_pivot(tmp_path: Path) -> None:
    # The whole point of the refactor: a correction phrase with no change in
    # tool direction must NOT be counted. Keywords no longer drive the signal.
    summary, turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["Read"]),
        _user_event("u1", "2026-06-15T10:00:05", "không phải, sai rồi, làm lại"),
        _assistant_event("a2", "2026-06-15T10:00:10", ["Read"]),
    ])
    assert summary.pivot_count == 0
    assert all(t.feedback_flag != "correction" for t in turns)
