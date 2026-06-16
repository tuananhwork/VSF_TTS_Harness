"""End-to-end Pattern pipeline: setup -> scan -> judge -> synth -> accept (interactive).

Usage:
    uv run e2e.py
    uv run e2e.py --sessions-dir data/sessions_synthetic_test  # skip scan, use existing dir
"""

from __future__ import annotations

import argparse
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


def _run(*args: str, extra_env: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    subprocess.run(args, check=True, cwd=ROOT, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sessions-dir",
        help="Skip scan.py and use this existing sessions directory instead.",
    )
    parser.add_argument("--min-recurrence", default="2")
    parser.add_argument("--max-deepdive", default="5")
    parser.add_argument(
        "--llm-provider",
        default="claude",
        metavar="PROVIDER",
        help="LLM provider: 'claude' (default) or 'ccs'.",
    )
    parser.add_argument(
        "--ccs-profile",
        default=None,
        metavar="NAME",
        help="CCS profile name (required when --llm-provider=ccs).",
    )
    args = parser.parse_args()

    provider = args.llm_provider.upper().replace("-", "_")
    is_ccs = provider in ("CCS", "CCS_ONE", "ONE")
    if is_ccs and not args.ccs_profile:
        parser.error("--ccs-profile NAME is required when --llm-provider=ccs")

    llm_env = {"LLM_PROVIDER": provider}
    if args.ccs_profile:
        llm_env["CCS_PROFILE"] = args.ccs_profile

    _run("uv", "sync")

    if args.sessions_dir:
        sessions_dir = Path(args.sessions_dir)
    else:
        _run(sys.executable, "scripts/scan.py")
        sessions_dir = _latest("sessions_*_runAt_*")
    print(f"[e2e] sessions: {sessions_dir}")

    _run(
        sys.executable, "scripts/judge.py",
        "--sessions-dir", str(sessions_dir),
        "--top-candidates", "5",
        "--min-recurrence", str(args.min_recurrence),
        "--max-deepdive", str(args.max_deepdive),
        extra_env=llm_env,
    )
    judge_dir = _latest("judge_*")
    print(f"[e2e] judge: {judge_dir}")

    _run(
        sys.executable, "scripts/synth.py",
        "--candidates", str(judge_dir / "candidate_skills.json"),
        "--top", "3", "--timeout", "300",
        extra_env=llm_env,
    )
    proposal_dir = _latest("skills_*_proposal")
    print(f"[e2e] proposal: {proposal_dir}")

    _run(sys.executable, str(proposal_dir / "accept.py"))


if __name__ == "__main__":
    main()
