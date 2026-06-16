"""Tests for the Claude Code log source (~/.claude/projects/<cwd>/<sid>.jsonl).

The inner message format is identical to cowork audit.jsonl, so `build_summary`
is reused; only metadata assembly (`build_cc_meta`) and discovery differ. These
tests cover that adapter layer:
  - title  ← `ai-title` line
  - intent ← first *real* user turn (skip <command-*> wrappers + isMeta)
  - model  ← first assistant `message.model`
  - timestamps → createdAt/lastActivityAt (epoch ms) for the date filter
  - sub-agent `isSidechain` turns are excluded
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import scan


def _asst(uuid: str, ts: str, *, model: str = "claude-opus-4-8",
          tools: list[str] | None = None, sidechain: bool = False) -> dict:
    content: list[dict] = [{"type": "text", "text": "ok"}]
    for i, name in enumerate(tools or []):
        content.append({"type": "tool_use", "name": name, "id": f"{uuid}-{i}", "input": {}})
    return {
        "type": "assistant", "uuid": uuid, "timestamp": ts, "isSidechain": sidechain,
        "message": {"model": model, "content": content,
                    "usage": {"input_tokens": 5, "output_tokens": 7}},
    }


def _user(uuid: str, ts: str, text: str, *, is_meta: bool = False,
          sidechain: bool = False) -> dict:
    return {
        "type": "user", "uuid": uuid, "timestamp": ts,
        "isMeta": is_meta, "isSidechain": sidechain,
        "message": {"content": text},
    }


def _write_transcript(path: Path, events: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return path


def _transcript(tmp_path: Path, events: list[dict]) -> Path:
    return _write_transcript(tmp_path / "9b783420-d248-4efb-9888-572387967d5a.jsonl", events)


# ── build_cc_meta ─────────────────────────────────────────────────────────────


def test_cc_meta_pulls_title_intent_model_times(tmp_path: Path) -> None:
    t = _transcript(tmp_path, [
        {"type": "ai-title", "aiTitle": "Fix the scanner", "sessionId": "s"},
        _user("u0", "2026-06-16T10:00:00.000Z",
              "<command-name>/clear</command-name>"),       # wrapper → skip
        _user("u1", "2026-06-16T10:00:01.000Z", "system note", is_meta=True),  # meta → skip
        _user("u2", "2026-06-16T10:00:02.000Z", "Sửa scan.py cho mình"),       # real intent
        _asst("a1", "2026-06-16T10:05:00.000Z", model="claude-opus-4-8"),
    ])
    meta = scan.build_cc_meta(t)
    assert meta["title"] == "Fix the scanner"
    assert meta["initialMessage"] == "Sửa scan.py cho mình"
    assert meta["model"] == "claude-opus-4-8"
    assert meta["sessionId"] == t.stem
    # earliest/latest timestamps as epoch ms → drives session_touches_dates
    assert scan.epoch_ms_to_date(meta["createdAt"]) == date(2026, 6, 16)
    assert meta["lastActivityAt"] >= meta["createdAt"]


def test_cc_meta_empty_transcript_is_safe(tmp_path: Path) -> None:
    meta = scan.build_cc_meta(_transcript(tmp_path, []))
    assert meta["title"] is None
    assert meta["initialMessage"] is None
    assert meta["model"] is None


# ── parse_claude_code_session ─────────────────────────────────────────────────


def test_cc_session_parses_turns_and_actions(tmp_path: Path) -> None:
    t = _transcript(tmp_path, [
        {"type": "ai-title", "aiTitle": "T", "sessionId": "s"},
        _user("u1", "2026-06-16T10:00:00.000Z", "do it"),
        _asst("a1", "2026-06-16T10:00:01.000Z", tools=["Bash", "Read"]),
    ])
    summary, turns, _ = scan.parse_claude_code_session(t, "C--repo")
    assert summary.title == "T"
    assert summary.intent_seed == "do it"
    assert summary.model == "claude-opus-4-8"
    assert summary.workspace_id == "C--repo"
    assert summary.total_actions == 2
    assert summary.total_user_turns == 1 and summary.total_assistant_turns == 1
    assert summary.outputs_produced == 0 and summary.uploads_produced == 0


def test_cc_session_excludes_sidechain(tmp_path: Path) -> None:
    t = _transcript(tmp_path, [
        _user("u1", "2026-06-16T10:00:00.000Z", "main task"),
        _asst("a1", "2026-06-16T10:00:01.000Z", tools=["Task"]),
        # Sub-agent sidechain turns — must NOT count toward the user trajectory.
        _user("s1", "2026-06-16T10:00:02.000Z", "subagent prompt", sidechain=True),
        _asst("s2", "2026-06-16T10:00:03.000Z", tools=["Grep", "Glob"], sidechain=True),
    ])
    summary, _turns, _ = scan.parse_claude_code_session(t, "ws")
    assert summary.total_turns == 2          # only main user + main assistant
    assert summary.total_actions == 1        # only the Task call
    assert "Grep" not in summary.tool_usage


def test_cc_session_passes_date_filter(tmp_path: Path) -> None:
    t = _transcript(tmp_path, [
        _user("u1", "2026-06-16T10:00:00.000Z", "hi"),
        _asst("a1", "2026-06-16T10:00:01.000Z"),
    ])
    meta = scan.build_cc_meta(t)
    assert scan.session_touches_dates(meta, [date(2026, 6, 16)]) is True
    assert scan.session_touches_dates(meta, [date(2026, 6, 17)]) is False
