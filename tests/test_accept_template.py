"""Verify the accept.py emitted by synth.py behaves correctly."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from synth import _emit_accept_py


def test_emitted_accept_installs_via_argv(tmp_path: Path) -> None:
    # Arrange: fake proposal dir with one candidate folder
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    skill_src = proposal / "summarize_pdf"
    skill_src.mkdir()
    (skill_src / "SKILL.md").write_text("hello", encoding="utf-8")
    _emit_accept_py(proposal, ["summarize_pdf"])

    fake_home = tmp_path / "home"
    # Inherit env so Python subprocess starts on Windows (needs SystemRoot
    # etc.), then override HOME/USERPROFILE so Path.home() resolves to the
    # temp dir. Cross-platform: HOME on POSIX, USERPROFILE on Windows.
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    result = subprocess.run(
        [sys.executable, str(proposal / "accept.py"), "1"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    installed = fake_home / ".claude" / "skills" / "summarize_pdf" / "SKILL.md"
    assert installed.exists()
    assert installed.read_text(encoding="utf-8") == "hello"
