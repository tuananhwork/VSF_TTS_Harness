"""Tests for scripts/_lib/trace_loader.py."""

from __future__ import annotations

import json
from pathlib import Path

from _lib.trace_loader import load_trace, load_traces


def _write_session(path: Path, session_id: str, turns: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(
            {"record_type": "session_summary", "session_id": session_id}
        ) + "\n")
        for t in turns:
            f.write(json.dumps({"record_type": "turn", **t}, ensure_ascii=False) + "\n")


def _turns() -> list[dict]:
    return [
        {"role": "user", "user_text": "Tóm tắt file", "feedback_flag": None,
         "actions": []},
        {"role": "assistant", "user_text": None, "feedback_flag": None,
         "actions": [{"tool_name": "Read"}, {"tool_name": "Edit"},
                     {"tool_name": "Edit"}]},
        {"role": "user", "user_text": "sai rồi, làm lại", "feedback_flag": "correction",
         "actions": []},
    ]


def test_load_trace_preserves_order_and_markers(tmp_path: Path) -> None:
    p = tmp_path / "sess.jsonl"
    _write_session(p, "sid-1", _turns())

    trace = load_trace(p)

    assert trace[0] == {"role": "user", "text": "Tóm tắt file", "feedback": None}
    assert trace[1] == {"role": "assistant", "tools": ["Read", "Edit×2"],
                        "feedback": None}
    assert trace[2]["role"] == "user"
    assert trace[2]["feedback"] == "correction"


def test_load_trace_truncates_long_text(tmp_path: Path) -> None:
    p = tmp_path / "sess.jsonl"
    _write_session(p, "sid-1", [
        {"role": "user", "user_text": "x" * 1000, "feedback_flag": None, "actions": []},
    ])
    trace = load_trace(p, max_text=50)
    assert len(trace[0]["text"]) <= 60  # 50 + ellipsis marker


def test_load_traces_keys_by_session_id(tmp_path: Path) -> None:
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    _write_session(p1, "sid-a", _turns())
    _write_session(p2, "sid-b", _turns())

    traces = load_traces(["a.jsonl", "b.jsonl"], tmp_path)
    assert set(traces) == {"sid-a", "sid-b"}
    assert traces["sid-a"][0]["text"] == "Tóm tắt file"
