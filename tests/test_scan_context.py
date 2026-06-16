"""Tests for scan.py context/coverage fields (data_goal L2/L5/L6).

Covers three gaps closed against the field spec:
  A. `focused_apps`  — window/app the user was pointing at, parsed from the
     `<cu_window_hints>` block embedded in a user turn (L5 domain marker).
  B. `uploads_produced` / `upload_names` / `outputs_names` — artifact signals;
     previously only a bare `outputs_produced` count existed.
  C. `skills_enabled` / `plugins_enabled` / `available_slash_commands` — pulled
     from the session metadata (L6 skill-override + "don't re-propose" context).
"""

from __future__ import annotations

import json
from pathlib import Path

import scan


def _write_audit(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _parse(tmp_path: Path, events: list[dict], meta: dict | None = None):
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, events)
    meta_path = tmp_path / "local_test.json"
    meta_path.write_text(json.dumps(meta or {}), encoding="utf-8")
    return scan.parse_session(meta_path, audit, "ws1")


def _user_event(uuid: str, text: str, *, is_replay: bool = False) -> dict:
    ev = {
        "type": "user",
        "uuid": uuid,
        "timestamp": "2026-06-15T10:00:00",
        "message": {"content": text},
    }
    if is_replay:
        ev["isReplay"] = True
    return ev


# ── Gap C: metadata context fields ────────────────────────────────────────────


def test_meta_context_fields_propagate(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(
        tmp_path,
        [_user_event("u1", "hi")],
        meta={
            "skillsEnabled": True,
            "pluginsEnabled": False,
            "slashCommands": ["pm:brainstorm", "review", "standup"],
        },
    )
    assert summary.skills_enabled is True
    assert summary.plugins_enabled is False
    assert summary.available_slash_commands == ["pm:brainstorm", "review", "standup"]


def test_meta_context_defaults_when_absent(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [_user_event("u1", "hi")], meta={})
    assert summary.skills_enabled is None
    assert summary.plugins_enabled is None
    assert summary.available_slash_commands == []


# ── Gap B: uploads + output/upload names ──────────────────────────────────────


def test_uploads_counted_and_named(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "spec.xlsx").write_text("x", encoding="utf-8")
    (uploads / "mock.png").write_text("y", encoding="utf-8")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "PRD.md").write_text("z", encoding="utf-8")

    summary, _turns, _ = _parse(tmp_path, [_user_event("u1", "hi")])

    assert summary.uploads_produced == 2
    assert sorted(summary.upload_names) == ["mock.png", "spec.xlsx"]
    assert summary.outputs_produced == 1
    assert summary.outputs_names == ["PRD.md"]


def test_uploads_zero_when_folder_absent(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [_user_event("u1", "hi")])
    assert summary.uploads_produced == 0
    assert summary.upload_names == []
    assert summary.outputs_names == []


# ── Gap A: focused_apps from cu_window_hints ──────────────────────────────────


def test_focused_apps_extracted_from_window_hints(tmp_path: Path) -> None:
    hint = (
        'Tóm tắt giúp tôi\n<cu_window_hints>The user is pointing at: window '
        '"conversation.txt - Notepad" (already open; pass '
        '"Microsoft.WindowsNotepad_8wekyb3d8bbwe!App" to request_access).'
        "</cu_window_hints>"
    )
    summary, _turns, _ = _parse(tmp_path, [_user_event("u1", hint)])
    assert summary.focused_apps == ["conversation.txt - Notepad"]


def test_focused_apps_dedupe_and_order(tmp_path: Path) -> None:
    def h(title: str) -> str:
        return f'<cu_window_hints>The user is pointing at: window "{title}" (x)</cu_window_hints>'

    summary, _turns, _ = _parse(
        tmp_path,
        [
            _user_event("u1", h("Chrome — Gmail")),
            _user_event("u2", h("VS Code")),
            _user_event("u3", h("Chrome — Gmail")),  # duplicate
        ],
    )
    assert summary.focused_apps == ["Chrome — Gmail", "VS Code"]


def test_focused_apps_empty_without_hints(tmp_path: Path) -> None:
    summary, _turns, _ = _parse(tmp_path, [_user_event("u1", "just a prompt")])
    assert summary.focused_apps == []
