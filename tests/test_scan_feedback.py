"""Tests for scan.py structural feedback signals (rework + failure).

`repeat` now means *rework after a failure* (retrying a tool that just errored),
not raw tool reuse — clean autonomous loops (screenshot×N, TaskCreate×N) must NOT
count. `failure_count` counts actions whose tool_result was an error.
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


def _tool_result_event(uuid: str, tool_use_id: str, *, is_error: bool) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": [{"type": "text", "text": "boom" if is_error else "ok"}],
                }
            ]
        },
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


# ── failure_count ─────────────────────────────────────────────────────────────


def test_failure_count_counts_errored_actions(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["bash", "Read"]),
        _tool_result_event("r1", "a1-0", is_error=True),    # bash failed
        _tool_result_event("r2", "a1-1", is_error=False),   # Read ok
    ])
    assert summary.failure_count == 1


def test_failure_count_zero_when_all_ok(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["bash"]),
        _tool_result_event("r1", "a1-0", is_error=False),
    ])
    assert summary.failure_count == 0


# ── repeat = rework after failure ─────────────────────────────────────────────


def test_repeat_flags_retry_after_failure(tmp_path: Path) -> None:
    summary, turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["bash"]),
        _tool_result_event("r1", "a1-0", is_error=True),     # bash failed
        _assistant_event("a2", "2026-06-15T10:00:10", ["bash"]),  # retry → rework
    ])
    assert summary.repeat_count == 1
    assert [t.feedback_flag for t in turns] == [None, "repeat"]


def test_clean_repeat_is_not_rework(tmp_path: Path) -> None:
    # The over-fire fix: re-running a tool that SUCCEEDED is normal, not rework.
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["TaskCreate"]),
        _tool_result_event("r1", "a1-0", is_error=False),
        _assistant_event("a2", "2026-06-15T10:00:05", ["TaskCreate"]),
        _assistant_event("a3", "2026-06-15T10:00:08", ["TaskCreate"]),
    ])
    assert summary.repeat_count == 0


def test_rework_not_flagged_outside_window(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["bash"]),
        _tool_result_event("r1", "a1-0", is_error=True),
        _assistant_event("a2", "2026-06-15T10:02:00", ["bash"]),  # 120s later
    ])
    assert summary.repeat_count == 0


def test_rework_requires_same_tool(tmp_path: Path) -> None:
    # bash failed, but the next turn uses a different tool → not rework.
    summary, _turns, _ = _parse(tmp_path, [
        _assistant_event("a1", "2026-06-15T10:00:00", ["bash"]),
        _tool_result_event("r1", "a1-0", is_error=True),
        _assistant_event("a2", "2026-06-15T10:00:10", ["Read"]),
    ])
    assert summary.repeat_count == 0
