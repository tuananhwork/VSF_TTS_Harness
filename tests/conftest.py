"""Shared pytest fixtures for Pattern tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Make scripts/ importable for tests that hit judge.py / synth.py helpers.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def sessions_dir() -> Path:
    """Directory containing 4 real session JSONL files from 2026-06-12 scan."""
    return FIXTURES_DIR / "sessions"
