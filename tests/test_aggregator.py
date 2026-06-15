"""Tests for scripts/_lib/aggregator.py."""

from __future__ import annotations

from pathlib import Path

from _lib.aggregator import Session, load_sessions


def test_load_sessions_reads_all_fixture_files(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    assert len(sessions) == 4
    assert all(isinstance(s, Session) for s in sessions)


def test_load_sessions_extracts_title_and_tools(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    titles = {s.title for s in sessions}
    assert "Computer use capabilities test" in titles
    fermat = next(s for s in sessions if s.process_name == "lucid-beautiful-fermat")
    assert fermat.total_actions > 0
    assert len(fermat.tool_usage) > 0
