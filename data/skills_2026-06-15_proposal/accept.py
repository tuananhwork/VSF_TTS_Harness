"""Interactive installer for Pattern skill drafts.

Usage:
    python accept.py            # interactive prompts
    python accept.py 1 3        # install candidates 1 and 3 non-interactive
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


CANDIDATES = ['test-and-report-ci-to-teams', 'write-short-prd', 'attach-to-running-desktop-app']
SKILLS_HOME = Path.home() / ".claude" / "skills"


def install(idx: int) -> None:
    if idx < 1 or idx > len(CANDIDATES):
        print(f"  ! index {idx} out of range")
        return
    name = CANDIDATES[idx - 1]
    src = Path(__file__).parent / name
    dst = SKILLS_HOME / name
    if not src.exists():
        print(f"  ! source folder missing: {src}")
        return
    if dst.exists():
        print(f"  ! {dst} already exists, skipping")
        return
    SKILLS_HOME.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    print(f"  + installed {name} -> {dst}")


def main() -> None:
    if not CANDIDATES:
        print("No candidates in this proposal.")
        return
    args = sys.argv[1:]
    if args:
        for raw in args:
            try:
                install(int(raw))
            except ValueError:
                print(f"  ! not a number: {raw}")
        return
    print("Pattern - skill proposal")
    print(f"Found {len(CANDIDATES)} candidate(s). Install which?")
    for i, name in enumerate(CANDIDATES, 1):
        print(f"  [{i}] {name}")
    raw = input("Enter numbers (comma-separated) or 'q' to quit: ").strip()
    if raw.lower() in {"q", "quit", "exit", ""}:
        return
    for tok in raw.split(","):
        try:
            install(int(tok.strip()))
        except ValueError:
            print(f"  ! not a number: {tok}")
    print("Done. Installed skills are active in the next Claude session.")


if __name__ == "__main__":
    main()
