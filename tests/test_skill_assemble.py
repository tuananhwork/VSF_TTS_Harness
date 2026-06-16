"""Tests for scripts/_lib/skill_assemble.py (deterministic folder builder)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from _lib.skill_assemble import assemble_skill, content_hash, decide_split


CANDIDATE = {
    "name": "test-and-report",
    "skill_type": "process_macro",
    "behavior_class": "process",
    "risk_flags": ["write_action"],
    "evidence": {"session_ids": ["s1", "s2"], "source_files": ["f1.jsonl"]},
    "metrics": {"recurrence": 2, "repeat_rate": 0.1, "failure_rate": 0.0},
    "good_points": ["dùng ToolSearch trước"],
    "weak_points": ["lặp bash 3 lần liên tiếp"],
    "improvement_notes": ["dùng .venv của dự án"],
    "debate": [{"judge": "efficiency", "stance": "approve", "axis_score": 4,
                "argument": "ổn"}],
}

RENDERED_SINGLE = {
    "description": "Run a project's tests and report CI status. Use for CI checks.",
    "when_to_use": "Use when asked to run a project's tests and report CI status.",
    "capabilities": [
        {
            "slug": "run-and-report",
            "title": "Run tests and report",
            "when": "always",
            "steps": ["Find the test tool", "Run pytest", "Report status"],
            "deterministic_script": {
                "name": "run_tests.sh",
                "purpose": "run the project test suite",
                "command": "uv run pytest",
            },
        }
    ],
    "red_flags": ["Re-running the same command after it already ran"],
    "core_lesson": "",
    "golden_tests": [
        {"query": "run tests for project X", "expected": "runs and reports"},
        {"query": "check CI status", "expected": "reports pass/fail"},
        {"query": "test and tell Teams", "expected": "runs then notifies"},
    ],
    "related": [],
}

RENDERED_MULTI = {
    **RENDERED_SINGLE,
    "capabilities": [
        {"slug": "run-tests", "title": "Run tests", "when": "first",
         "steps": ["a", "b"]},
        {"slug": "report-teams", "title": "Report to Teams", "when": "after",
         "steps": ["c", "d"]},
    ],
}

NOW = datetime(2026, 6, 16, 9, 30)


def test_decide_split_on_capability_count() -> None:
    assert decide_split(RENDERED_SINGLE) is False
    assert decide_split(RENDERED_MULTI) is True


def test_assemble_single_capability_inline_no_references(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    assert d.name == "test-and-report"
    assert not (d / "references").exists()
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "## When to use" in skill
    assert "Run pytest" in skill                 # steps inline
    assert "name: test-and-report" in skill
    assert "skill_type: process_macro" in skill
    # Pure instruction: no provenance leaks into SKILL.md.
    assert "s1" not in skill and "generated_on" not in skill


def test_assemble_writes_honest_script_stub(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    stub = (d / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
    assert "STUB" in stub                        # honest: marked not-yet-verified
    assert "uv run pytest" in stub


def test_assemble_writes_evidence_with_raw_vietnamese(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=NOW)
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    ev_dirs = list((d / "evidence").iterdir())
    assert len(ev_dirs) == 1
    assert ev_dirs[0].name == f"20260616-0930_{content_hash(skill)}"
    ev = (ev_dirs[0] / "evidence.md").read_text(encoding="utf-8")
    assert "s1" in ev                            # session ids live here
    assert "lặp bash 3 lần liên tiếp" in ev      # raw VI evidence preserved
    assert "efficiency" in ev                    # debate verdict


def test_assemble_multi_capability_splits_references(tmp_path: Path) -> None:
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_MULTI,
                       output_dir=tmp_path, now=NOW)
    refs = sorted(p.name for p in (d / "references").glob("*.md"))
    assert refs == ["report-teams.md", "run-tests.md"]
    skill = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "references/run-tests.md" in skill
    assert "references/report-teams.md" in skill
    # Index does not inline the steps when split.
    detail = (d / "references" / "run-tests.md").read_text(encoding="utf-8")
    assert "Run tests" in detail


def test_assemble_evidence_idempotent_on_same_content(tmp_path: Path) -> None:
    assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                   output_dir=tmp_path, now=NOW)
    # Second run, LATER time, identical content → no second evidence dir.
    later = datetime(2026, 6, 16, 10, 45)
    d = assemble_skill(candidate=CANDIDATE, rendered=RENDERED_SINGLE,
                       output_dir=tmp_path, now=later)
    assert len(list((d / "evidence").iterdir())) == 1
