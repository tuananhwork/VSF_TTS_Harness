"""Tests for scripts/_lib/skill_validate.py (code-side quality gate)."""

from __future__ import annotations

from pathlib import Path

from _lib.skill_validate import validate_skill


def _make_skill(tmp_path: Path, folder: str, frontmatter: str, body: str) -> Path:
    d = tmp_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return d


def test_validate_passes_clean_skill(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: When to use foo. Use for X.\nmetadata:\n  skill_type: process_macro\n",
        "# foo\n\n## When to use\n\nUse it for X.\n",
    )
    assert validate_skill(d) == []


def test_validate_flags_extra_frontmatter_key(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\nextra: nope\n",
        "# foo\n",
    )
    assert any("frontmatter keys" in p for p in validate_skill(d))


def test_validate_flags_name_folder_mismatch(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: bar\ndescription: d\nmetadata: {}\n",
        "# bar\n",
    )
    assert any("!= folder" in p for p in validate_skill(d))


def test_validate_flags_empty_description(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: ''\nmetadata: {}\n",
        "# foo\n",
    )
    assert any("description" in p for p in validate_skill(d))


def test_validate_flags_birth_history_leak(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n\n## Evidence\n\ngenerated_on: 2026-06-16\n",
    )
    probs = validate_skill(d)
    assert any("birth-history" in p for p in probs)


def test_validate_flags_orphan_reference(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n",
    )
    (d / "references").mkdir()
    (d / "references" / "orphan.md").write_text("# orphan\n", encoding="utf-8")
    assert any("orphan" in p for p in validate_skill(d))


def test_validate_flags_missing_linked_reference(tmp_path: Path) -> None:
    d = _make_skill(
        tmp_path, "foo",
        "name: foo\ndescription: d\nmetadata: {}\n",
        "# foo\n\nSee [detail](references/ghost.md).\n",
    )
    assert any("ghost" in p for p in validate_skill(d))
