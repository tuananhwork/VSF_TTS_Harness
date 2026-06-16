"""Lượt 3 — Skill synthesis.

For each top-N accepted candidate:
  1. render_skill (LLM, the one reasoning call) → English skill content as JSON.
  2. assemble_skill (code) → deterministic skill folder (SKILL.md, references/,
     scripts/ stubs, golden_tests.md, evidence/<time>_<hash>/).
  3. validate_skill (code) → quality gate; problems surface in PROPOSAL.md.

Writes PROPOSAL.md + accept.py under data/skills_<date>_proposal/.

Usage:
    python scripts/synth.py --candidates data/judge_<date>/candidate_skills.json \\
        [--top 3] [--timeout 120]
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date as _date
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime  # noqa: E402

from _lib.candidate_schema import normalize_skill_name  # noqa: E402
from _lib.skill_render import render_skill  # noqa: E402
from _lib.skill_assemble import assemble_skill  # noqa: E402
from _lib.skill_validate import validate_skill  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent


def _emit_accept_py(out_dir: Path, skill_names: list[str]) -> None:
    """Write a self-contained accept.py with the candidate names baked in."""
    script = '''"""Interactive installer for Pattern skill drafts.

Usage:
    python accept.py            # interactive prompts
    python accept.py 1 3        # install candidates 1 and 3 non-interactive
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


CANDIDATES = {names!r}
SKILLS_HOME = Path.home() / ".claude" / "skills"


def install(idx: int) -> None:
    if idx < 1 or idx > len(CANDIDATES):
        print(f"  ! index {{idx}} out of range")
        return
    name = CANDIDATES[idx - 1]
    src = Path(__file__).parent / name
    dst = SKILLS_HOME / name
    if not src.exists():
        print(f"  ! source folder missing: {{src}}")
        return
    if dst.exists():
        print(f"  ! {{dst}} already exists, skipping")
        return
    SKILLS_HOME.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    print(f"  + installed {{name}} -> {{dst}}")


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
                print(f"  ! not a number: {{raw}}")
        return
    print("Pattern - skill proposal")
    print(f"Found {{len(CANDIDATES)}} candidate(s). Install which?")
    for i, name in enumerate(CANDIDATES, 1):
        print(f"  [{{i}}] {{name}}")
    raw = input("Enter numbers (comma-separated) or 'q' to quit: ").strip()
    if raw.lower() in {{"q", "quit", "exit", ""}}:
        return
    for tok in raw.split(","):
        try:
            install(int(tok.strip()))
        except ValueError:
            print(f"  ! not a number: {{tok}}")
    print("Done. Installed skills are active in the next Claude session.")


if __name__ == "__main__":
    main()
'''.format(names=skill_names)
    (out_dir / "accept.py").write_text(script, encoding="utf-8")


def _synthesize_one(
    candidate: dict, batch_names: list[str], out_dir: Path, timeout: float,
    now: datetime,
) -> dict:
    """Render (LLM) → assemble (code) → validate (code). Returns candidate plus
    the quality-gate result under `synth_problems`."""
    rendered = render_skill(candidate, batch_names, timeout=timeout)
    skill_dir = assemble_skill(
        candidate=candidate, rendered=rendered, output_dir=out_dir, now=now,
    )
    problems = validate_skill(skill_dir)
    if problems:
        click.echo(f"  ! quality gate flagged {skill_dir.name}: {'; '.join(problems)}")
    return {**candidate, "synth_problems": problems}


@click.command()
@click.option(
    "--candidates", "candidates_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--top", type=int, default=3, show_default=True)
@click.option("--timeout", type=float, default=120.0, show_default=True)
def main(candidates_path: Path, top: int, timeout: float) -> None:
    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"skills_{today}_proposal"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    accepted = [c for c in all_candidates if not c.get("rejected_reason")]
    top_n = [normalize_skill_name(c) for c in accepted[:top]]
    batch_names = [c["name"] for c in top_n]
    click.echo(f"[synth] {len(top_n)} candidates to synthesize")

    now = datetime.now()
    results: list[dict] = []
    for c in top_n:
        click.echo(f"[synth] -> {c['name']}")
        results.append(_synthesize_one(c, batch_names, out_dir, timeout, now))

    # Save sidecar meta and emit accept.py
    (out_dir / "_proposal_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _emit_accept_py(out_dir, [c["name"] for c in results])

    # Render PROPOSAL.md + a deterministic quality-gate section.
    from _lib.render_proposal import render_pattern_report
    proposal_md = render_pattern_report(
        date=today,
        date_range=str(candidates_path.parent.name),
        sessions_scanned=0,  # not tracked in synth, see judge step's report
        clusters=[],
        candidates=results,
    )
    gate_lines = [
        f"- `{c['name']}`: " + ("OK" if not c.get("synth_problems")
                                 else "; ".join(c["synth_problems"]))
        for c in results
    ]
    proposal_md += "\n## Synth quality gate\n\n" + "\n".join(gate_lines) + "\n"
    (out_dir / "PROPOSAL.md").write_text(proposal_md, encoding="utf-8")
    click.echo(f"[synth] done -> {out_dir}")


if __name__ == "__main__":
    main()
