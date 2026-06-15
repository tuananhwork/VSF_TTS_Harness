"""Tests for scan.py ordered tool_sequence extraction."""

from __future__ import annotations

import json
from pathlib import Path

import scan


def _assistant_event(uuid: str, tool_names: list[str]) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "message": {
            "content": [
                {"type": "tool_use", "name": name, "id": f"{uuid}-{i}", "input": {}}
                for i, name in enumerate(tool_names)
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }


def _write_audit(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def test_tool_sequence_preserves_order_and_compresses_runs(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, [
        _assistant_event("a1", ["Read", "Grep"]),
        _assistant_event("a2", ["Edit", "Edit", "Bash"]),
    ])
    meta = tmp_path / "local_test.json"
    meta.write_text("{}", encoding="utf-8")

    summary, _turns, _rl = scan.parse_session(meta, audit, "ws1")

    # Order preserved across turns; consecutive duplicates compressed.
    assert summary.tool_sequence == ["Read", "Grep", "Edit×2", "Bash"]
    # Count dict still independent of ordering.
    assert summary.tool_usage["Edit"] == 2
