"""Tests cho refactored pipeline functions."""
from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_run_scan_returns_path_and_calls_log(tmp_path, monkeypatch):
    """run_scan() trả về Path và gọi log_fn ít nhất 1 lần."""
    import scan

    monkeypatch.setattr(scan, "DATA_ROOT", tmp_path)

    fake_root = tmp_path / "fake_logs"
    fake_root.mkdir()
    monkeypatch.setattr(scan, "_detect_log_root", lambda source: fake_root)

    logs = []
    result = scan.run_scan(source="claude-cowork", target_date="", log_fn=logs.append)

    assert isinstance(result, Path)
    assert result.exists()
    assert len(logs) > 0


def test_run_judge_returns_path(tmp_path, monkeypatch):
    """run_judge() trả về Path tới candidate_skills.json."""
    import judge
    from pathlib import Path

    monkeypatch.setattr(judge, "DATA_ROOT", tmp_path)

    sessions_dir = tmp_path / "sessions_test"
    sessions_dir.mkdir()

    monkeypatch.setattr(judge, "load_sessions", lambda d: [])
    monkeypatch.setattr(judge, "aggregate", lambda s: [])

    logs = []
    result = judge.run_judge(
        sessions_dir=sessions_dir,
        min_recurrence=2,
        max_deepdive=5,
        top_candidates=5,
        timeout=30.0,
        log_fn=logs.append,
    )

    assert isinstance(result, Path)
    assert result.name == "candidate_skills.json"
    assert result.exists()
    assert len(logs) > 0


def test_run_synth_returns_results_and_path(tmp_path, monkeypatch):
    """run_synth() với 0 accepted candidates trả về (list rỗng, Path out_dir)."""
    import synth

    monkeypatch.setattr(synth, "DATA_ROOT", tmp_path)

    candidates_path = tmp_path / "candidate_skills.json"
    candidates_path.write_text(
        '[{"name": "test-skill", "rejected_reason": "low score"}]',
        encoding="utf-8",
    )

    logs = []
    results, out_dir = synth.run_synth(
        candidates_path=candidates_path,
        top=3,
        timeout=30.0,
        log_fn=logs.append,
    )

    assert isinstance(results, list)
    assert isinstance(out_dir, Path)
    assert out_dir.exists()
    assert len(logs) > 0


def test_run_synth_emits_status_per_candidate(tmp_path, monkeypatch):
    """status_fn nhận 1 dòng 'Sinh skill' cho mỗi candidate được synthesize."""
    import synth

    import _lib.render_proposal as rp

    monkeypatch.setattr(synth, "DATA_ROOT", tmp_path)
    # Skip the real LLM render/assemble; just echo back a finished candidate.
    monkeypatch.setattr(
        synth, "_synthesize_one",
        lambda c, batch, out, timeout, now, runner: {**c, "synth_problems": []},
    )
    # Report rendering is unrelated to the status emission under test.
    monkeypatch.setattr(rp, "render_pattern_report", lambda **_: "")

    candidates_path = tmp_path / "candidate_skills.json"
    candidates_path.write_text(
        '[{"name": "test-skill"}]', encoding="utf-8",
    )

    statuses: list[str] = []
    synth.run_synth(
        candidates_path=candidates_path, top=3, timeout=30.0,
        log_fn=lambda *_: None, status_fn=statuses.append,
    )
    assert any("Sinh skill" in s for s in statuses)
    assert any("test-skill" in s for s in statuses)
