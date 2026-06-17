"""Tests for the GUI Running screen's live activity bar (Phase 1 streaming UX)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# gui/ isn't on the default test path (conftest adds scripts/ only).
_GUI = Path(__file__).resolve().parent.parent / "gui"
if str(_GUI) not in sys.path:
    sys.path.insert(0, str(_GUI))

ft = pytest.importorskip("flet")

from screen_running import RunningScreen  # noqa: E402


class _FakePage:
    def __init__(self) -> None:
        self.services: list = []

    def update(self) -> None:  # pragma: no cover - not exercised here
        pass


def _screen() -> RunningScreen:
    return RunningScreen(_FakePage(), on_cancel=lambda: None)


def test_activity_bar_hidden_by_default() -> None:
    rs = _screen()
    assert rs._activity_bar.visible is False


def test_set_activity_shows_bar_with_label() -> None:
    rs = _screen()
    rs.set_activity("Triage · 3 nhóm")
    assert rs._activity_bar.visible is True
    assert rs._activity_text.value == "Triage · 3 nhóm"


def test_tick_elapsed_appends_seconds_once_per_second() -> None:
    rs = _screen()
    rs.set_activity("Trích xuất: x (1/2)")
    rs._activity_start -= 3.2          # simulate ~3s elapsed
    assert rs.tick_elapsed() is True   # label changed → caller should update()
    assert "Trích xuất: x (1/2)" in rs._activity_text.value
    assert "3s" in rs._activity_text.value
    assert rs.tick_elapsed() is False  # same second → no change


def test_clear_activity_hides_bar_and_stops_ticking() -> None:
    rs = _screen()
    rs.set_activity("Tổng hợp: x (2/2)")
    rs.clear_activity()
    assert rs._activity_bar.visible is False
    assert rs.tick_elapsed() is False  # no active label → nothing to tick


def test_reset_clears_activity() -> None:
    rs = _screen()
    rs.set_activity("Sinh skill: x (1/1)")
    rs.reset()
    assert rs._activity_bar.visible is False
