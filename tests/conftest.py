"""Shared pytest fixtures for Pattern tests."""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sessions_dir() -> Path:
    """Directory containing 4 real session JSONL files from 2026-06-12 scan."""
    return FIXTURES_DIR / "sessions"
