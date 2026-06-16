"""Stage 2 of synth: deterministically build a skill folder from a candidate plus
the Stage-1 rendered content. No LLM here — pure file/string construction, so the
whole thing is unit-testable.

Layout produced under `<output_dir>/<slug>/`:
  SKILL.md                          # instruction-only (inline or index)
  references/<slug>.md              # only when >1 capability
  scripts/<name>                    # only for capabilities with a deterministic step
  golden_tests.md
  evidence/<YYYYMMDD-HHMM>_<hash8>/evidence.md   # all provenance
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from _lib.candidate_schema import slugify_skill_name

_TEMPLATES_DIR = Path(__file__).parent / "synth_templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def content_hash(text: str) -> str:
    """First 8 hex chars of sha256 — identifies one SKILL.md revision."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def decide_split(rendered: dict[str, Any]) -> bool:
    """Split into references/ when the skill has more than one capability."""
    return len(rendered.get("capabilities") or []) > 1


def _as_block(value: Any) -> str:
    """Normalize a str | list into a markdown block for evidence."""
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value or "").strip()


def _evidence_hash_present(evidence_dir: Path, hash8: str) -> bool:
    if not evidence_dir.exists():
        return False
    return any(
        p.is_dir() and p.name.endswith(f"_{hash8}") for p in evidence_dir.iterdir()
    )


def assemble_skill(
    *,
    candidate: dict[str, Any],
    rendered: dict[str, Any],
    output_dir: Path,
    now: datetime,
) -> Path:
    """Build (or refresh) the skill folder for one candidate. Returns its path.

    `now` is injected (not read from the clock) so output is reproducible in tests.
    """
    name = slugify_skill_name(candidate["name"])
    skill_dir = output_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_type = candidate.get("skill_type", "process_macro")
    capabilities = rendered.get("capabilities") or []
    split = decide_split(rendered)

    # --- SKILL.md (inline single capability OR index of references) ---
    skill_md = _env.get_template("skill_index.md.j2").render(
        name=name,
        description=rendered["description"],
        skill_type=skill_type,
        risk_flags=candidate.get("risk_flags") or [],
        when_to_use=rendered.get("when_to_use", ""),
        core_lesson=rendered.get("core_lesson") or "",
        capabilities=capabilities,
        split=split,
        red_flags=rendered.get("red_flags") or [],
        related=rendered.get("related") or [],
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # --- references/<slug>.md (only when split) ---
    if split:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(exist_ok=True)
        for cap in capabilities:
            (refs_dir / f"{cap['slug']}.md").write_text(
                _env.get_template("skill_reference.md.j2").render(cap=cap),
                encoding="utf-8",
            )

    # --- scripts/<name> honest stubs for deterministic capabilities ---
    scripts = [
        c["deterministic_script"]
        for c in capabilities
        if c.get("deterministic_script")
    ]
    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for sc in scripts:
            (scripts_dir / sc["name"]).write_text(
                _env.get_template("skill_script_stub.j2").render(
                    purpose=sc.get("purpose", ""), command=sc.get("command", "")
                ),
                encoding="utf-8",
            )

    # --- golden_tests.md ---
    (skill_dir / "golden_tests.md").write_text(
        _env.get_template("skill_golden.md.j2").render(
            name=name, golden_tests=rendered.get("golden_tests") or []
        ),
        encoding="utf-8",
    )

    # --- evidence/<time>_<hash>/evidence.md (skip if this content already logged) ---
    hash8 = content_hash(skill_md)
    evidence_dir = skill_dir / "evidence"
    if not _evidence_hash_present(evidence_dir, hash8):
        target = evidence_dir / f"{now.strftime('%Y%m%d-%H%M')}_{hash8}"
        target.mkdir(parents=True, exist_ok=True)
        ev = candidate.get("evidence", {}) or {}
        (target / "evidence.md").write_text(
            _env.get_template("skill_evidence.md.j2").render(
                name=name,
                skill_type=skill_type,
                behavior_class=candidate.get("behavior_class", ""),
                generated_on=now.strftime("%Y-%m-%d"),
                hash8=hash8,
                session_ids=ev.get("session_ids", []),
                source_files=ev.get("source_files", []),
                metrics=candidate.get("metrics"),
                good_points=candidate.get("good_points") or [],
                weak_points=candidate.get("weak_points") or [],
                improvement_notes=_as_block(candidate.get("improvement_notes")),
                debate=candidate.get("debate") or [],
            ),
            encoding="utf-8",
        )

    return skill_dir
