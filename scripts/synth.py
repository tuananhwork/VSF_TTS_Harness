"""Lượt 3 — Skill synthesis with skill-creator headless + template fallback.

Usage:
    python scripts/synth.py --candidates data/judge_<date>/candidate_skills.json \\
        [--top 3] [--timeout 120]

For each top-N accepted candidate:
- Path A: ask `ccs one -p` to use the skill-creator skill, output to a per-skill
  folder. If SKILL.md exists after the call, mark synth_path = "A".
- Path B: if A fails (timeout or no file), fall back to a smaller `ccs one -p`
  call that fills the Jinja templates with steps + 3 golden tests.

Writes PROPOSAL.md + accept.py under data/skills_<date>_proposal/.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date as _date
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.claude_runner import (  # noqa: E402
    ClaudeRunError,
    run_claude,
    run_claude_json,
)
from _lib.candidate_schema import slugify_skill_name  # noqa: E402
from _lib.render_proposal import build_skill_description, render_skill_dir  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent


def _path_a_prompt(candidate: dict, skill_dir: Path) -> str:
    skill_type = candidate.get("skill_type", "process_macro")
    name = skill_dir.name
    description = build_skill_description(candidate)
    return f"""Use the skill-creator skill. Create a new skill with these inputs.

NAME: {name}
DESCRIPTION: {description}
SKILL_TYPE: {skill_type}
TRIGGER (VI): {candidate['trigger_intent']['vi']}
TRIGGER (EN): {candidate['trigger_intent']['en']}
BEHAVIOR_CLASS: {candidate.get('behavior_class', 'process')}
ACTION_TEMPLATE_JSON (ordered flow): {json.dumps(candidate.get('action_template', []), ensure_ascii=False)}
GOOD_POINTS: {json.dumps(candidate.get('good_points', []), ensure_ascii=False)}
WEAK_POINTS: {json.dumps(candidate.get('weak_points', []), ensure_ascii=False)}
IMPROVEMENT_NOTES: {candidate.get('improvement_notes', '')}
EVIDENCE_SESSION_IDS: {", ".join(candidate.get('evidence', {}).get('session_ids', []))}
RISK_FLAGS: {", ".join(candidate.get('risk_flags', []))}

OUTPUT FOLDER (absolute): {skill_dir}

Requirements:
- Write SKILL.md whose YAML frontmatter conforms to the Agent Skills spec
  (https://agentskills.io/specification). The frontmatter MUST have exactly two
  required keys at the top level — `name` and `description` — plus an optional
  `metadata:` block. Do NOT put any other keys at the top level.
  - `name`: use exactly `{name}` (it already matches this output folder; lowercase
    letters/digits/hyphens only, no underscores).
  - `description`: a single string (<= 1024 chars) stating what the skill does and
    when to use it. Use this value verbatim: {description}
  - Put `skill_type`, `behavior_class`, and `risk_flags` under `metadata:` as
    string values — never as top-level frontmatter keys.
- If SKILL_TYPE is process_macro: document the ordered flow (step 1→2→3→4) from
  ACTION_TEMPLATE_JSON so the user can re-run it quickly.
- If SKILL_TYPE is improvement_lesson: centre the skill on WEAK_POINTS +
  IMPROVEMENT_NOTES — what went wrong last time and what to do first next time
  to avoid it. Keep the flow as supporting context.
- Write golden_tests.md with 3 test cases derived from evidence.
- Create scripts/ folder if action has deterministic steps; otherwise omit it.
- If risk_flags include write_action or deletes_files, the skill must include
  an explicit confirm step before any side-effect tool call.
"""


def _path_b_fill_prompt(candidate: dict) -> str:
    return f"""Given this skill candidate JSON, produce ONLY the values that
fill a Jinja2 template (no prose, no markdown fences, return JSON):

CANDIDATE:
{json.dumps(candidate, ensure_ascii=False, indent=2)}

Output STRICT JSON with shape:
{{
  "steps_markdown": "<markdown bullet list of 3-5 numbered steps>",
  "golden_test_1": {{"query": "...", "expected": "..."}},
  "golden_test_2": {{"query": "...", "expected": "..."}},
  "golden_test_3": {{"query": "...", "expected": "..."}}
}}
"""


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


def _synthesize_one(candidate: dict, out_dir: Path, timeout: float) -> str:
    """Returns synth_path: 'A' or 'B'."""
    skill_dir = out_dir / slugify_skill_name(candidate["name"])
    skill_dir.mkdir(parents=True, exist_ok=True)
    today = _date.today().isoformat()

    try:
        run_claude(_path_a_prompt(candidate, skill_dir), timeout=timeout)
    except ClaudeRunError as e:
        click.echo(f"  ! Path A failed for {candidate['name']}: {e}")
    if (skill_dir / "SKILL.md").exists():
        return "A"

    click.echo(f"  -> falling back to Path B for {candidate['name']}")
    filled = run_claude_json(_path_b_fill_prompt(candidate), timeout=min(60.0, timeout))
    render_skill_dir(
        candidate=candidate, filled=filled,
        output_dir=out_dir, generated_on=today,
    )
    return "B"


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
    top_n = accepted[:top]
    click.echo(f"[synth] {len(top_n)} candidates to synthesize")

    results: list[dict] = []
    for c in top_n:
        # Canonicalize the name once so the folder, accept.py, and PROPOSAL all agree.
        c = {**c, "name": slugify_skill_name(c["name"])}
        click.echo(f"[synth] -> {c['name']}")
        synth_path = _synthesize_one(c, out_dir, timeout)
        results.append({**c, "synth_path": synth_path})

    # Save sidecar meta and emit accept.py
    (out_dir / "_proposal_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _emit_accept_py(out_dir, [c["name"] for c in results])

    # Render PROPOSAL.md
    from _lib.render_proposal import render_pattern_report
    proposal_md = render_pattern_report(
        date=today,
        date_range=str(candidates_path.parent.name),
        sessions_scanned=0,  # not tracked in synth, see judge step's report
        clusters=[],
        candidates=results,
    )
    (out_dir / "PROPOSAL.md").write_text(proposal_md, encoding="utf-8")
    click.echo(f"[synth] done -> {out_dir}")


if __name__ == "__main__":
    main()
