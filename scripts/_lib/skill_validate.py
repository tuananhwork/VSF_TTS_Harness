"""Code-side quality gate for an assembled skill folder. No LLM.

Returns a list of human-readable problems; an empty list means the skill passes.
This is the deterministic backstop for the rules we don't trust the render LLM to
keep: spec-clean frontmatter, name==folder, no birth-history leaking back into
SKILL.md, and references that line up with the index.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Substrings that must never appear in SKILL.md body — they are provenance /
# "how I was born", which belongs in evidence/, not in the instructions.
_BIRTH_MARKERS = ("generated_on", "generated_by", "## Evidence", "rút từ session")


def validate_skill(skill_dir: Path) -> list[str]:
    """Validate one assembled skill folder. Empty list == pass."""
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"missing SKILL.md in {skill_dir}"]
    text = skill_md.read_text(encoding="utf-8")

    parts = text.split("---", 2)
    if len(parts) < 3:
        return ["SKILL.md has no YAML frontmatter"]
    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML: {e}"]
    body = parts[2]

    # 1. Exactly the three spec-allowed top-level keys.
    keys = set(front)
    if keys != {"name", "description", "metadata"}:
        problems.append(
            f"frontmatter keys {sorted(keys)} != ['description', 'metadata', 'name']"
        )

    # 2. name matches folder and is a valid slug.
    name = str(front.get("name", ""))
    if name != skill_dir.name:
        problems.append(f"name '{name}' != folder '{skill_dir.name}'")
    if not _SLUG_RE.match(name) or len(name) > 64:
        problems.append(f"name '{name}' is not a valid skill slug")

    # 3. description present, non-empty, <= 1024 chars.
    desc = front.get("description")
    if not isinstance(desc, str) or not (0 < len(desc) <= 1024):
        problems.append("description must be a non-empty string <= 1024 chars")

    # 4. No birth-history leaking into the instructions.
    for marker in _BIRTH_MARKERS:
        if marker in body:
            problems.append(f"SKILL.md leaks birth-history marker: '{marker}'")

    # 5. References line up with the index (no missing links, no orphans).
    refs_dir = skill_dir / "references"
    linked = set(re.findall(r"references/([a-z0-9-]+)\.md", text))
    on_disk = {p.stem for p in refs_dir.glob("*.md")} if refs_dir.exists() else set()
    for miss in sorted(linked - on_disk):
        problems.append(f"index links references/{miss}.md but the file is missing")
    for orphan in sorted(on_disk - linked):
        problems.append(f"references/{orphan}.md exists but is not linked from index")

    return problems
