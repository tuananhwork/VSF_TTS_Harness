"""End-to-end Pattern pipeline: setup -> scan -> judge -> synth -> accept (interactive).

Usage:
    uv run e2e.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _latest(pattern: str) -> Path:
    dirs = sorted(DATA.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dirs:
        raise SystemExit(f"[e2e] no directory matching {pattern!r} found under data/")
    return dirs[0]


def _run(*args: str) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(args, check=True, cwd=ROOT, env=env)


def main() -> None:
    _run("uv", "sync")

    _run(sys.executable, "scripts/scan.py")
    sessions_dir = _latest("sessions_*_runAt_*")
    print(f"[e2e] sessions: {sessions_dir}")

    _run(
        sys.executable, "scripts/judge.py",
        "--sessions-dir", str(sessions_dir),
        "--min-size", "2", "--top-candidates", "5",
    )
    judge_dir = _latest("judge_*")
    print(f"[e2e] judge: {judge_dir}")

    _run(
        sys.executable, "scripts/synth.py",
        "--candidates", str(judge_dir / "candidate_skills.json"),
        "--top", "3", "--timeout", "120",
    )
    proposal_dir = _latest("skills_*_proposal")
    print(f"[e2e] proposal: {proposal_dir}")

    _run(sys.executable, str(proposal_dir / "accept.py"))


if __name__ == "__main__":
    main()
