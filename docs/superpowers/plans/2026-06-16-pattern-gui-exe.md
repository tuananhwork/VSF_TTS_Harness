# Pattern GUI (.exe) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đóng gói pipeline Pattern thành `Pattern.exe` — user double-click, chọn ngày, cài skill, không cần terminal hay Python.

**Architecture:** 3 màn hình CustomTkinter (Configure → Running → Review) wired qua `PatternApp`. Pipeline chạy trong background thread, giao tiếp với GUI qua `queue.Queue`. Scripts Python hiện tại được refactor thành importable functions và bundle vào .exe bằng PyInstaller.

**Tech Stack:** Python 3.12, customtkinter 5.x, tkcalendar (date picker), PyInstaller 6.x, click (giữ nguyên cho CLI), threading + queue (GUI/pipeline bridge)

---

## File Structure

```
gui/
├── app.py                  # PatternApp(CTk) — window, screen switching
├── screen_configure.py     # ConfigureScreen — form input
├── screen_running.py       # RunningScreen — step status + log
├── screen_review.py        # ReviewScreen — skill cards + install
└── pipeline_runner.py      # PipelineRunner(Thread) + PipelineParams + SkillProposal

scripts/
├── scan.py                 # MODIFY: extract run_scan(), replace print→log_fn
├── judge.py                # MODIFY: extract run_judge(), replace click.echo→log_fn
└── synth.py                # MODIFY: extract run_synth(), replace click.echo→log_fn

tests/
└── test_pipeline_runner.py # unit tests cho pipeline_runner + refactored run fns

assets/
└── pattern.ico             # app icon (16x16 + 32x32 ICO)

build_exe.py                # PyInstaller build script
pyproject.toml              # thêm customtkinter, tkcalendar, pyinstaller
```

---

## Task 1: Thêm dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Thêm deps vào pyproject.toml**

```toml
[project]
name = "pattern"
version = "0.1.0"
description = "Behavior → Skill harness for Claude Cowork"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "jinja2>=3.1",
    "click>=8.1",
    "customtkinter>=5.2",
    "tkcalendar>=1.6",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pyyaml>=6.0",
    "pyinstaller>=6.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
```

- [ ] **Step 2: Sync và verify**

```bash
uv sync
```

Expected: resolves without error. `uv run python -c "import customtkinter; print(customtkinter.__version__)"` in ra version ≥ 5.2.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add customtkinter, tkcalendar, pyinstaller deps"
```

---

## Task 2: Refactor scan.py — extract run_scan()

**Files:**
- Modify: `scripts/scan.py`
- Test: `tests/test_pipeline_runner.py` (skeleton)

**Nguyên tắc:** Tách body của `main()` thành `run_scan()`. `main()` trở thành thin wrapper. Thay `print()` bằng `log_fn`. Không thay đổi logic.

- [ ] **Step 1: Viết failing test**

Tạo `tests/test_pipeline_runner.py`:

```python
"""Tests cho refactored pipeline functions."""
from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_run_scan_returns_path_and_calls_log(tmp_path, monkeypatch):
    """run_scan() trả về Path và gọi log_fn ít nhất 1 lần."""
    import scan

    # Trỏ DATA_ROOT về tmp_path để không ghi vào data/ thật
    monkeypatch.setattr(scan, "DATA_ROOT", tmp_path)

    # Fake log root trỏ về folder rỗng → 0 session, vẫn chạy được
    fake_root = tmp_path / "fake_logs"
    fake_root.mkdir()
    monkeypatch.setattr(scan, "_detect_log_root", lambda source: fake_root)

    logs = []
    result = scan.run_scan(source="claude-cowork", target_date="", log_fn=logs.append)

    assert isinstance(result, Path)
    assert result.exists()
    assert len(logs) > 0
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_scan_returns_path_and_calls_log -v
```

Expected: `FAILED` vì `scan.run_scan` chưa tồn tại.

- [ ] **Step 3: Refactor scan.py**

Trong `scripts/scan.py`, thêm hàm `run_scan()` ngay trước `main()`:

```python
def run_scan(
    source: str = SOURCE_COWORK,
    target_date: str | None = None,
    log_fn=print,
) -> Path:
    """Scan sessions và write JSONL ra out_dir. Trả về out_dir path."""
    root = _detect_log_root(source)
    targets = parse_target_dates(target_date)
    label = target_label(targets)
    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = DATA_ROOT / f"sessions_{label}_runAt_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict[str, Any]] = []
    scanned = matched = 0
    for summary, turns, rate_limits, ok in _iter_parsed(source, root, targets):
        scanned += 1
        if not ok:
            continue
        matched += 1
        out_path = write_session(out_dir, summary, turns, rate_limits)
        index.append({
            "session_id": summary.session_id,
            "title": summary.title,
            "model": summary.model,
            "created_at": summary.created_at,
            "duration_seconds": summary.duration_seconds,
            "total_turns": summary.total_turns,
            "total_actions": summary.total_actions,
            "file": out_path.name,
        })
        log_fn(f"  + {summary.process_name or summary.session_id} -> {out_path.name}")

    (out_dir / "_index.json").write_text(
        json.dumps({
            "source": source,
            "target_date": label,
            "run_at": run_ts,
            "source_root": str(root),
            "scanned": scanned,
            "matched": matched,
            "sessions": index,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log_fn(f"\nDone. {matched}/{scanned} {source} sessions matched {label} -> {out_dir}")
    return out_dir
```

Sửa `main()` thành thin wrapper:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Claude session logs -> per-session JSONL.")
    parser.add_argument(
        "--source", choices=[SOURCE_COWORK, SOURCE_CLAUDE_CODE], default=SOURCE_COWORK,
    )
    parser.add_argument("--target-date", default=None, metavar="SPEC")
    args = parser.parse_args(argv)
    run_scan(source=args.source, target_date=args.target_date)
    return 0
```

- [ ] **Step 4: Chạy test — xác nhận PASS**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_scan_returns_path_and_calls_log -v
```

Expected: `PASSED`.

- [ ] **Step 5: Verify CLI vẫn chạy**

```bash
uv run python scripts/scan.py --help
```

Expected: hiển thị help text không lỗi.

- [ ] **Step 6: Commit**

```bash
git add scripts/scan.py tests/test_pipeline_runner.py
git commit -m "refactor(scan): extract run_scan() for GUI import"
```

---

## Task 3: Refactor judge.py — extract run_judge()

**Files:**
- Modify: `scripts/judge.py`
- Modify: `tests/test_pipeline_runner.py`

- [ ] **Step 1: Viết failing test**

Thêm vào `tests/test_pipeline_runner.py`:

```python
def test_run_judge_returns_path(tmp_path, monkeypatch):
    """run_judge() trả về Path tới candidate_skills.json."""
    import judge
    from pathlib import Path

    monkeypatch.setattr(judge, "DATA_ROOT", tmp_path)

    # Tạo sessions_dir giả với 0 file — judge sẽ bỏ qua LLM call
    sessions_dir = tmp_path / "sessions_test"
    sessions_dir.mkdir()

    # Mock load_sessions trả về list rỗng → skip LLM
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
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_judge_returns_path -v
```

Expected: `FAILED` vì `judge.run_judge` chưa tồn tại.

- [ ] **Step 3: Refactor judge.py**

Thêm `run_judge()` ngay trước `@click.command()`:

```python
def run_judge(
    sessions_dir: Path,
    min_recurrence: int = 2,
    max_deepdive: int = 5,
    top_candidates: int = 5,
    timeout: float = 300.0,
    installed_skills_dir: Path | None = None,
    log_fn=print,
) -> Path:
    """Chạy judge pipeline. Trả về Path tới candidate_skills.json."""
    if installed_skills_dir is None:
        installed_skills_dir = Path.home() / ".claude" / "skills"

    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"judge_{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log_fn(f"[judge] loading sessions from {sessions_dir}")
    sessions = load_sessions(sessions_dir)
    log_fn(f"[judge] loaded {len(sessions)} sessions")

    clusters = aggregate(sessions)
    cluster_dicts = [c.to_dict() for c in clusters]
    (out_dir / "cluster_summary.json").write_text(
        json.dumps(cluster_dicts, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    log_fn(f"[judge] {len(clusters)} tool-usage group(s)")

    if not clusters:
        log_fn("[judge] no sessions → skipping LLM judge")
        final: list[dict] = []
        accepted: list[dict] = []
    else:
        installed = _list_installed_skills(installed_skills_dir)

        log_fn(f"[judge] triage: `{provider_label()}` (timeout={timeout}s)")
        triage_prompt = build_triage_prompt(cluster_dicts, installed)
        triage = run_claude_json(triage_prompt, timeout=timeout)
        (out_dir / "_raw_triage.txt").write_text(
            json.dumps(triage, ensure_ascii=False, indent=2), encoding="utf-8")
        triage = [normalize_skill_name(normalize_skill_type(c)) for c in triage]
        triage = recompute_candidate_metrics(triage, sessions)
        triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
        accepted_triage, rejected = split_accepted(triage)
        log_fn(f"[judge] triage: {len(accepted_triage)} pass, {len(rejected)} rejected")
        accepted_triage = accepted_triage[:max_deepdive]

        enriched: list[dict] = []
        for c in accepted_triage:
            src = c.get("evidence", {}).get("source_files", [])
            traces = load_traces(src, sessions_dir)
            log_fn(f"[judge] debate: {c['name']} ({len(traces)} traces, {len(JUDGES)} judges)")

            try:
                facts = run_claude_json(build_extract_prompt(c, traces), timeout=timeout)
                (out_dir / f"_raw_extract_{c['name']}.txt").write_text(
                    json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
            except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
                log_fn(f"[judge]   ! extract failed ({e})")
                facts = {"extract_error": str(e)}

            verdicts = run_debate(
                c, facts, traces, judges=JUDGES, runner=run_claude_json, timeout=timeout
            )
            (out_dir / f"_raw_debate_{c['name']}.txt").write_text(
                json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")

            try:
                verdict = run_claude_json(
                    build_consolidator_prompt(c, facts, verdicts), timeout=timeout)
                (out_dir / f"_raw_consolidate_{c['name']}.txt").write_text(
                    json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
            except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
                log_fn(f"[judge]   ! consolidator failed ({e}); keeping candidate")
                verdict = {"consolidator_error": str(e)}

            enriched.append({**c, **facts, "debate": verdicts, **verdict})

        accepted = [c for c in enriched if not c.get("rejected_reason")]
        accepted = sorted(
            accepted,
            key=lambda c: sum(c.get("final_score", c.get("prelim_score", {})).values()),
            reverse=True,
        )[:top_candidates]
        rejected += [c for c in enriched if c.get("rejected_reason")]
        final = accepted + rejected

    candidates_path = out_dir / "candidate_skills.json"
    candidates_path.write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    report_md = render_pattern_report(
        date=today,
        date_range=str(sessions_dir.name),
        sessions_scanned=len(sessions),
        clusters=cluster_dicts,
        candidates=final,
    )
    (out_dir / "pattern_report.md").write_text(report_md, encoding="utf-8")
    log_fn(f"[judge] done. {len(accepted)} accepted, {len(final) - len(accepted)} rejected → {out_dir}")
    return candidates_path
```

Sửa `@click.command()` thành thin wrapper:

```python
@click.command()
@click.option("--sessions-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--installed-skills-dir", type=click.Path(file_okay=False, path_type=Path), default=Path.home() / ".claude" / "skills")
@click.option("--top-candidates", type=int, default=5)
@click.option("--min-recurrence", type=int, default=2)
@click.option("--max-deepdive", type=int, default=5)
@click.option("--timeout", type=float, default=300.0)
def main(sessions_dir, installed_skills_dir, top_candidates, min_recurrence, max_deepdive, timeout):
    run_judge(
        sessions_dir=sessions_dir,
        min_recurrence=min_recurrence,
        max_deepdive=max_deepdive,
        top_candidates=top_candidates,
        timeout=timeout,
        installed_skills_dir=installed_skills_dir,
    )
```

- [ ] **Step 4: Chạy test — xác nhận PASS**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_judge_returns_path -v
```

Expected: `PASSED`.

- [ ] **Step 5: Verify CLI vẫn chạy**

```bash
uv run python scripts/judge.py --help
```

Expected: help text không lỗi.

- [ ] **Step 6: Commit**

```bash
git add scripts/judge.py tests/test_pipeline_runner.py
git commit -m "refactor(judge): extract run_judge() for GUI import"
```

---

## Task 4: Refactor synth.py — extract run_synth()

**Files:**
- Modify: `scripts/synth.py`
- Modify: `tests/test_pipeline_runner.py`

- [ ] **Step 1: Viết failing test**

Thêm vào `tests/test_pipeline_runner.py`:

```python
def test_run_synth_returns_results_and_path(tmp_path, monkeypatch):
    """run_synth() với 0 accepted candidates trả về (list rỗng, Path out_dir)."""
    import synth

    monkeypatch.setattr(synth, "DATA_ROOT", tmp_path)

    # candidates_path rỗng (0 accepted)
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
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_synth_returns_results_and_path -v
```

Expected: `FAILED`.

- [ ] **Step 3: Refactor synth.py**

Thêm `run_synth()` ngay trước `@click.command()`:

```python
def run_synth(
    candidates_path: Path,
    top: int = 3,
    timeout: float = 120.0,
    log_fn=print,
) -> list[dict]:
    """Synthesize top-N candidates. Trả về list dict kết quả (có thể rỗng)."""
    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"skills_{today}_proposal"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    accepted = [c for c in all_candidates if not c.get("rejected_reason")]
    top_n = [normalize_skill_name(c) for c in accepted[:top]]
    batch_names = [c["name"] for c in top_n]
    log_fn(f"[synth] {len(top_n)} candidates to synthesize")

    now = datetime.now()
    results: list[dict] = []
    for c in top_n:
        log_fn(f"[synth] -> {c['name']}")
        results.append(_synthesize_one(c, batch_names, out_dir, timeout, now))

    (out_dir / "_proposal_meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _emit_accept_py(out_dir, [c["name"] for c in results])

    from _lib.render_proposal import render_pattern_report as _render
    proposal_md = _render(
        date=today,
        date_range=str(candidates_path.parent.name),
        sessions_scanned=0,
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
    log_fn(f"[synth] done -> {out_dir}")
    return results, out_dir
```

Sửa `@click.command()` thành thin wrapper:

```python
@click.command()
@click.option("--candidates", "candidates_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--top", type=int, default=3)
@click.option("--timeout", type=float, default=120.0)
def main(candidates_path: Path, top: int, timeout: float) -> None:
    run_synth(candidates_path=candidates_path, top=top, timeout=timeout)
```

- [ ] **Step 4: Chạy test — xác nhận PASS**

```bash
uv run pytest tests/test_pipeline_runner.py::test_run_synth_returns_results_and_path -v
```

Expected: `PASSED`.

- [ ] **Step 5: Chạy toàn bộ test suite**

```bash
uv run pytest -v
```

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/synth.py tests/test_pipeline_runner.py
git commit -m "refactor(synth): extract run_synth() for GUI import"
```

---

## Task 5: pipeline_runner.py

**Files:**
- Create: `gui/pipeline_runner.py`

Định nghĩa dataclasses, protocol queue, và background thread.

- [ ] **Step 1: Tạo thư mục gui/**

```bash
mkdir gui
```

- [ ] **Step 2: Tạo gui/pipeline_runner.py**

```python
"""Background pipeline thread + message protocol cho Pattern GUI."""
from __future__ import annotations

import queue
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

# Thêm scripts/ vào path để import scan, judge, synth
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import scan as _scan
import judge as _judge
import synth as _synth


@dataclass
class PipelineParams:
    date: str           # "YYYY-MM-DD" hoặc "" (hôm nay)
    source: str         # "claude-cowork" | "claude-code"
    min_recurrence: int = 2
    max_deepdive: int = 5
    top_candidates: int = 5
    timeout: float = 300.0


@dataclass
class SkillProposal:
    name: str
    description: str
    recurrence: int
    confidence: str     # "cao" | "trung bình" | "thấp"
    folder_path: Path
    has_quality_issues: bool = False


# Queue message types:
#   ("log", str)                     — log line
#   ("step_start", str)              — "scan" | "judge" | "synth"
#   ("step_done", str)               — step succeeded
#   ("step_error", str, str)         — step name, error message
#   ("done", list[SkillProposal])    — pipeline finished
#   ("no_sessions", None)            — 0 sessions found
#   ("no_candidates", None)          — 0 patterns found


def _score_to_confidence(candidate: dict) -> str:
    score = sum(candidate.get("final_score", candidate.get("prelim_score", {})).values())
    if score >= 6:
        return "cao"
    if score >= 3:
        return "trung bình"
    return "thấp"


def _to_proposals(results: list[dict], out_dir: Path) -> list[SkillProposal]:
    proposals = []
    for c in results:
        folder = out_dir / c["name"]
        if not folder.exists():
            continue
        proposals.append(SkillProposal(
            name=c["name"],
            description=c.get("trigger_intent") or c.get("name", ""),
            recurrence=c.get("metrics", {}).get("recurrence", 0),
            confidence=_score_to_confidence(c),
            folder_path=folder,
            has_quality_issues=bool(c.get("synth_problems")),
        ))
    return proposals


class PipelineRunner(threading.Thread):
    def __init__(self, params: PipelineParams, q: queue.Queue):
        super().__init__(daemon=True)
        self._params = params
        self._q = q
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _log(self, msg: str) -> None:
        self._q.put(("log", msg))

    def run(self) -> None:
        p = self._params

        # ── Scan ────────────────────────────────────────────────
        self._q.put(("step_start", "scan"))
        try:
            sessions_dir = _scan.run_scan(
                source=p.source,
                target_date=p.date,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "scan", str(e)))
            return

        # Check 0 sessions
        index_path = sessions_dir / "_index.json"
        if index_path.exists():
            import json
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            if idx.get("matched", 0) == 0:
                self._q.put(("step_done", "scan"))
                self._q.put(("no_sessions", None))
                return

        self._q.put(("step_done", "scan"))
        if self._cancelled.is_set():
            return

        # ── Judge ────────────────────────────────────────────────
        self._q.put(("step_start", "judge"))
        try:
            candidates_path = _judge.run_judge(
                sessions_dir=sessions_dir,
                min_recurrence=p.min_recurrence,
                max_deepdive=p.max_deepdive,
                top_candidates=p.top_candidates,
                timeout=p.timeout,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "judge", str(e)))
            return

        self._q.put(("step_done", "judge"))
        if self._cancelled.is_set():
            return

        # ── Synth ────────────────────────────────────────────────
        self._q.put(("step_start", "synth"))
        try:
            results, out_dir = _synth.run_synth(
                candidates_path=candidates_path,
                top=p.top_candidates,
                timeout=p.timeout,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "synth", str(e)))
            return

        self._q.put(("step_done", "synth"))

        if not results:
            self._q.put(("no_candidates", None))
            return

        proposals = _to_proposals(results, out_dir)
        self._q.put(("done", proposals))


def install_skill(proposal: SkillProposal) -> None:
    """Copy skill folder vào ~/.claude/skills/<name>/."""
    skills_home = Path.home() / ".claude" / "skills"
    skills_home.mkdir(parents=True, exist_ok=True)
    dst = skills_home / proposal.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(proposal.folder_path, dst)
```

- [ ] **Step 3: Chạy import test nhanh**

```bash
uv run python -c "import sys; sys.path.insert(0,'gui'); from pipeline_runner import PipelineParams, PipelineRunner, SkillProposal; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add gui/pipeline_runner.py
git commit -m "feat(gui): add PipelineRunner + PipelineParams + SkillProposal"
```

---

## Task 6: screen_configure.py

**Files:**
- Create: `gui/screen_configure.py`

- [ ] **Step 1: Tạo gui/screen_configure.py**

```python
"""Màn hình 1 — Configure: chọn ngày, source, tùy chọn nâng cao."""
from __future__ import annotations

from datetime import date
from typing import Callable

import customtkinter as ctk
from tkcalendar import DateEntry


class ConfigureScreen(ctk.CTkFrame):
    def __init__(self, master, on_run: Callable[..., None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_run = on_run
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(self, text="Pattern", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, pady=(24, 4), padx=24, sticky="w"
        )
        ctk.CTkLabel(self, text="Phân tích hành vi Claude → gợi ý Skill").grid(
            row=1, column=0, padx=24, sticky="w"
        )

        # Date
        ctk.CTkLabel(self, text="Ngày phân tích", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=24, pady=(20, 4), sticky="w"
        )
        self._date_entry = DateEntry(
            self,
            width=16,
            date_pattern="yyyy-mm-dd",
            year=date.today().year,
            month=date.today().month,
            day=date.today().day,
        )
        self._date_entry.grid(row=3, column=0, padx=24, sticky="w")

        # Source
        ctk.CTkLabel(self, text="Nguồn log", font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, padx=24, pady=(16, 4), sticky="w"
        )
        self._source_var = ctk.StringVar(value="claude-cowork")
        source_frame = ctk.CTkFrame(self, fg_color="transparent")
        source_frame.grid(row=5, column=0, padx=24, sticky="w")
        ctk.CTkRadioButton(source_frame, text="claude-cowork (Desktop)", variable=self._source_var,
                           value="claude-cowork").pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(source_frame, text="claude-code (CLI)", variable=self._source_var,
                           value="claude-code").pack(side="left")

        # Advanced (collapsible)
        self._adv_open = ctk.BooleanVar(value=False)
        adv_toggle = ctk.CTkButton(
            self, text="▶ Tùy chọn nâng cao", anchor="w",
            fg_color="transparent", text_color=("gray30", "gray70"),
            hover=False, command=self._toggle_advanced,
        )
        adv_toggle.grid(row=6, column=0, padx=20, pady=(16, 0), sticky="w")
        self._adv_toggle_btn = adv_toggle

        self._adv_frame = ctk.CTkFrame(self)
        self._adv_frame.grid(row=7, column=0, padx=24, pady=(4, 0), sticky="ew")
        self._adv_frame.grid_remove()  # hidden by default

        ctk.CTkLabel(self._adv_frame, text="Min recurrence").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        self._min_rec = ctk.CTkEntry(self._adv_frame, width=60)
        self._min_rec.insert(0, "2")
        self._min_rec.grid(row=0, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="Max deepdive").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._max_dd = ctk.CTkEntry(self._adv_frame, width=60)
        self._max_dd.insert(0, "5")
        self._max_dd.grid(row=1, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="LLM provider").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        self._provider_var = ctk.StringVar(value="claude")
        ctk.CTkOptionMenu(self._adv_frame, values=["claude", "ccs"],
                          variable=self._provider_var).grid(row=2, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="CCS profile").grid(row=3, column=0, padx=8, pady=4, sticky="w")
        self._ccs_entry = ctk.CTkEntry(self._adv_frame, width=120, placeholder_text="tên profile")
        self._ccs_entry.grid(row=3, column=1, padx=8)

        # Run button
        ctk.CTkButton(self, text="Chạy Pipeline", height=40,
                      command=self._on_run_click).grid(
            row=8, column=0, padx=24, pady=24, sticky="ew"
        )

    def _toggle_advanced(self) -> None:
        if self._adv_open.get():
            self._adv_frame.grid_remove()
            self._adv_toggle_btn.configure(text="▶ Tùy chọn nâng cao")
            self._adv_open.set(False)
        else:
            self._adv_frame.grid()
            self._adv_toggle_btn.configure(text="▼ Tùy chọn nâng cao")
            self._adv_open.set(True)

    def _on_run_click(self) -> None:
        try:
            min_rec = int(self._min_rec.get())
            max_dd = int(self._max_dd.get())
        except ValueError:
            min_rec, max_dd = 2, 5

        self._on_run(
            date=self._date_entry.get_date().isoformat(),
            source=self._source_var.get(),
            min_recurrence=min_rec,
            max_deepdive=max_dd,
        )
```

- [ ] **Step 2: Smoke test import**

```bash
uv run python -c "import sys; sys.path.insert(0,'gui'); import customtkinter as ctk; from screen_configure import ConfigureScreen; print('OK')"
```

Expected: `OK` (không mở cửa sổ).

- [ ] **Step 3: Commit**

```bash
git add gui/screen_configure.py
git commit -m "feat(gui): add ConfigureScreen"
```

---

## Task 7: screen_running.py

**Files:**
- Create: `gui/screen_running.py`

- [ ] **Step 1: Tạo gui/screen_running.py**

```python
"""Màn hình 2 — Running: step status + log output."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

_STEPS = ["scan", "judge", "synth"]
_STEP_LABELS = {"scan": "Scan", "judge": "Judge", "synth": "Synth"}
_ICONS = {"pending": "○", "running": "⏳", "done": "✓", "error": "✗"}


class RunningScreen(ctk.CTkFrame):
    def __init__(self, master, on_cancel: Callable[[], None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_cancel = on_cancel
        self._step_labels: dict[str, ctk.CTkLabel] = {}
        self._log_lines: list[str] = []
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Đang chạy pipeline...",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=(24, 12), padx=24, sticky="w"
        )

        # Step indicators
        steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        steps_frame.grid(row=1, column=0, padx=24, sticky="ew")
        for i, step in enumerate(_STEPS):
            lbl = ctk.CTkLabel(steps_frame,
                               text=f"{_ICONS['pending']}  {_STEP_LABELS[step]}",
                               font=ctk.CTkFont(size=13))
            lbl.grid(row=i, column=0, pady=3, sticky="w")
            self._step_labels[step] = lbl

        # Log area
        self._log_box = ctk.CTkTextbox(self, height=220, state="disabled",
                                        font=ctk.CTkFont(family="Consolas", size=11))
        self._log_box.grid(row=2, column=0, padx=24, pady=(16, 0), sticky="nsew")
        self.grid_rowconfigure(2, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=24, pady=16, sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_frame, text="Huỷ", width=80, fg_color="gray40",
                      command=self._on_cancel).grid(row=0, column=0, sticky="w")
        self._copy_btn = ctk.CTkButton(btn_frame, text="Copy log 📋", width=100,
                                        command=self._copy_log)
        self._copy_btn.grid(row=0, column=2, sticky="e")

    def reset(self) -> None:
        """Reset về trạng thái ban đầu để chạy pipeline mới."""
        self._log_lines = []
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        for step in _STEPS:
            self._set_step("pending", step)

    def update_step(self, status: str, step: str) -> None:
        """status: 'running' | 'done' | 'error'"""
        self._set_step(status, step)

    def append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def append_error(self, msg: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"ERROR: {msg}\n", "error")
        self._log_box.tag_config("error", foreground="red")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_step(self, status: str, step: str) -> None:
        icon = _ICONS.get(status, "○")
        color = {"done": "green", "error": "red", "running": "orange"}.get(status)
        lbl = self._step_labels[step]
        lbl.configure(text=f"{icon}  {_STEP_LABELS[step]}")
        if color:
            lbl.configure(text_color=color)

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(self._log_lines))
```

- [ ] **Step 2: Smoke test import**

```bash
uv run python -c "import sys; sys.path.insert(0,'gui'); from screen_running import RunningScreen; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add gui/screen_running.py
git commit -m "feat(gui): add RunningScreen"
```

---

## Task 8: screen_review.py

**Files:**
- Create: `gui/screen_review.py`

- [ ] **Step 1: Tạo gui/screen_review.py**

```python
"""Màn hình 3 — Review & Accept: chọn skill để cài."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

# Import SkillProposal — thêm gui/ vào path nếu cần
import sys
from pathlib import Path
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from pipeline_runner import SkillProposal, install_skill

_CONFIDENCE_COLOR = {
    "cao": "green",
    "trung bình": "orange",
    "thấp": "gray",
}


class ReviewScreen(ctk.CTkFrame):
    def __init__(self, master, on_back: Callable[[], None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_back = on_back
        self._proposals: list[SkillProposal] = []
        self._checkboxes: list[ctk.BooleanVar] = []
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._header = ctk.CTkLabel(self, text="",
                                     font=ctk.CTkFont(size=16, weight="bold"))
        self._header.grid(row=0, column=0, pady=(24, 8), padx=24, sticky="w")

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.grid(row=1, column=0, padx=24, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=24, pady=16, sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_frame, text="← Quay lại", width=100,
                      fg_color="gray40", command=self._on_back).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(btn_frame, text="Cài skill đã chọn", height=36,
                      command=self._install_selected).grid(row=0, column=2, sticky="e")

    def load_proposals(self, proposals: list[SkillProposal]) -> None:
        """Load danh sách proposal mới vào màn hình."""
        self._proposals = proposals
        self._checkboxes = []

        # Xoá cards cũ
        for w in self._scroll.winfo_children():
            w.destroy()

        self._header.configure(
            text=f"Phát hiện {len(proposals)} skill. Chọn để cài:"
        )

        for i, p in enumerate(proposals):
            var = ctk.BooleanVar(value=True)
            self._checkboxes.append(var)
            self._build_card(i, p, var)

    def _build_card(self, idx: int, p: SkillProposal, var: ctk.BooleanVar) -> None:
        card = ctk.CTkFrame(self._scroll, border_width=1)
        card.grid(row=idx, column=0, pady=4, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkCheckBox(card, text="", variable=var, width=24).grid(
            row=0, column=0, rowspan=2, padx=(12, 0), pady=8
        )
        ctk.CTkLabel(card, text=p.name,
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, padx=8, pady=(8, 0), sticky="w"
        )

        desc = p.description[:80] + "..." if len(p.description) > 80 else p.description
        ctk.CTkLabel(card, text=desc,
                     text_color=("gray40", "gray60")).grid(
            row=1, column=1, padx=8, sticky="w"
        )

        meta = f"Lặp {p.recurrence} lần  •  Độ tin cậy: {p.confidence}"
        if p.has_quality_issues:
            meta += "  ⚠"
        ctk.CTkLabel(card, text=meta,
                     text_color=_CONFIDENCE_COLOR.get(p.confidence, "gray"),
                     font=ctk.CTkFont(size=11)).grid(
            row=2, column=1, padx=8, pady=(0, 8), sticky="w"
        )

    def _install_selected(self) -> None:
        installed = []
        for proposal, var in zip(self._proposals, self._checkboxes):
            if var.get():
                try:
                    install_skill(proposal)
                    installed.append(proposal.name)
                except Exception as e:
                    pass  # Lỗi sẽ hiện qua toast nếu cần

        msg = (
            f"Đã cài {len(installed)} skill: {', '.join(installed)}.\n"
            "Có hiệu lực phiên Claude tiếp theo."
            if installed
            else "Không có skill nào được chọn."
        )
        import tkinter.messagebox as mb
        mb.showinfo("Pattern", msg)
```

- [ ] **Step 2: Smoke test import**

```bash
uv run python -c "import sys; sys.path.insert(0,'gui'); from screen_review import ReviewScreen; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add gui/screen_review.py
git commit -m "feat(gui): add ReviewScreen"
```

---

## Task 9: app.py — wiring toàn bộ

**Files:**
- Create: `gui/app.py`

- [ ] **Step 1: Tạo gui/app.py**

```python
"""Pattern GUI — main app entry point."""
from __future__ import annotations

import queue
import sys
from pathlib import Path

import customtkinter as ctk

# Thêm gui/ vào path
_GUI = Path(__file__).resolve().parent
if str(_GUI) not in sys.path:
    sys.path.insert(0, str(_GUI))

from pipeline_runner import PipelineParams, PipelineRunner, SkillProposal
from screen_configure import ConfigureScreen
from screen_running import RunningScreen
from screen_review import ReviewScreen

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

_POLL_MS = 50  # ms giữa mỗi lần đọc queue


class PatternApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pattern")
        self.geometry("500x560")
        self.resizable(False, False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._q: queue.Queue = queue.Queue()
        self._runner: PipelineRunner | None = None

        self._configure = ConfigureScreen(self, on_run=self._start_pipeline)
        self._running = RunningScreen(self, on_cancel=self._cancel_pipeline)
        self._review = ReviewScreen(self, on_back=self._show_configure)

        self._show_configure()

    # ── Screen switching ──────────────────────────────────────────────────────

    def _show_configure(self) -> None:
        self._running.grid_remove()
        self._review.grid_remove()
        self._configure.grid(row=0, column=0, sticky="nsew")

    def _show_running(self) -> None:
        self._configure.grid_remove()
        self._review.grid_remove()
        self._running.grid(row=0, column=0, sticky="nsew")

    def _show_review(self, proposals: list[SkillProposal]) -> None:
        self._running.grid_remove()
        self._configure.grid_remove()
        self._review.load_proposals(proposals)
        self._review.grid(row=0, column=0, sticky="nsew")

    # ── Pipeline control ──────────────────────────────────────────────────────

    def _start_pipeline(self, date: str, source: str,
                        min_recurrence: int, max_deepdive: int) -> None:
        params = PipelineParams(
            date=date,
            source=source,
            min_recurrence=min_recurrence,
            max_deepdive=max_deepdive,
        )
        self._running.reset()
        self._show_running()
        self._runner = PipelineRunner(params, self._q)
        self._runner.start()
        self.after(_POLL_MS, self._poll_queue)

    def _cancel_pipeline(self) -> None:
        if self._runner:
            self._runner.cancel()
        self._show_configure()

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass

        # Tiếp tục poll nếu runner còn chạy
        if self._runner and self._runner.is_alive():
            self.after(_POLL_MS, self._poll_queue)

    def _handle_msg(self, msg: tuple) -> None:
        kind = msg[0]

        if kind == "log":
            self._running.append_log(msg[1])

        elif kind == "step_start":
            self._running.update_step("running", msg[1])

        elif kind == "step_done":
            self._running.update_step("done", msg[1])

        elif kind == "step_error":
            step, err = msg[1], msg[2]
            self._running.update_step("error", step)
            self._running.append_error(err)

        elif kind == "no_sessions":
            self._running.append_log("Không có session nào cho ngày này. Thử ngày khác.")

        elif kind == "no_candidates":
            self._running.append_log("Chưa phát hiện pattern đủ mạnh. Thử quét nhiều ngày hơn.")

        elif kind == "done":
            proposals: list[SkillProposal] = msg[1]
            self._show_review(proposals)


def main() -> None:
    app = PatternApp()
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Chạy app để kiểm tra visual**

```bash
uv run python gui/app.py
```

Expected: cửa sổ mở, màn hình Configure hiển thị. Click "Chạy Pipeline" → chuyển sang Running. Kiểm tra 3 bước hiện đúng. Nút "Huỷ" quay về Configure.

- [ ] **Step 3: Commit**

```bash
git add gui/app.py
git commit -m "feat(gui): add PatternApp wiring 3 screens"
```

---

## Task 10: Fix DATA_ROOT cho frozen exe

**Files:**
- Modify: `scripts/scan.py`, `scripts/judge.py`, `scripts/synth.py`

Khi chạy dưới dạng `.exe`, `Path(__file__)` trỏ vào temp extraction dir của PyInstaller — không phải thư mục user. `DATA_ROOT` cần được redirect sang thư mục bên cạnh `.exe` để output được lưu đúng chỗ.

- [ ] **Step 1: Thêm helper `get_data_root()` vào scan.py**

Trong `scripts/scan.py`, thêm sau dòng `PROJECT_ROOT = ...`:

```python
def _get_data_root() -> Path:
    """Trả về data dir phù hợp với cả dev mode và frozen .exe."""
    import sys as _sys
    if getattr(_sys, "frozen", False):
        # Chạy từ .exe: lưu data bên cạnh file .exe
        return Path(_sys.executable).parent / "pattern_data"
    return Path(__file__).resolve().parent.parent / "data"

DATA_ROOT = _get_data_root()
```

Xoá dòng `DATA_ROOT = PROJECT_ROOT / "data"` cũ.

- [ ] **Step 2: Áp dụng tương tự cho judge.py**

Trong `scripts/judge.py`, thay:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
```

Thành:

```python
def _get_data_root() -> Path:
    import sys as _sys
    if getattr(_sys, "frozen", False):
        return Path(_sys.executable).parent / "pattern_data"
    return Path(__file__).resolve().parent.parent / "data"

DATA_ROOT = _get_data_root()
```

- [ ] **Step 3: Áp dụng tương tự cho synth.py**

Trong `scripts/synth.py`, thay:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
```

Thành:

```python
def _get_data_root() -> Path:
    import sys as _sys
    if getattr(_sys, "frozen", False):
        return Path(_sys.executable).parent / "pattern_data"
    return Path(__file__).resolve().parent.parent / "data"

DATA_ROOT = _get_data_root()
```

- [ ] **Step 4: Chạy lại toàn bộ tests**

```bash
uv run pytest -v
```

Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/scan.py scripts/judge.py scripts/synth.py
git commit -m "fix: redirect DATA_ROOT to exe-adjacent dir when frozen"
```

---

## Task 11: build_exe.py + đóng gói

**Files:**
- Create: `build_exe.py`
- Create: `assets/pattern.ico` (placeholder)

- [ ] **Step 1: Tạo placeholder icon**

```bash
python -c "
from pathlib import Path
Path('assets').mkdir(exist_ok=True)
# Tạo ICO tối giản 1x1 pixel (sẽ thay bằng icon thật sau)
ico_bytes = bytes([
    0,0,1,0,1,0,1,1,0,0,1,0,32,0,40,0,0,0,22,0,0,0,
    40,0,0,0,1,0,0,0,2,0,0,0,1,0,32,0,0,0,0,0,8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    0,0,0,255,0,0,0,0
])
Path('assets/pattern.ico').write_bytes(ico_bytes)
print('OK')
"
```

- [ ] **Step 2: Tạo build_exe.py**

```python
"""Build Pattern.exe via PyInstaller."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "Pattern",
    "--icon", str(ROOT / "assets" / "pattern.ico"),
    # Bundle _lib scripts
    "--add-data", f"{ROOT / 'scripts' / '_lib'}{';' if sys.platform == 'win32' else ':'}scripts/_lib",
    # Entry point
    str(ROOT / "gui" / "app.py"),
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build"),
    "--specpath", str(ROOT),
]

print("Building Pattern.exe...")
print(" ".join(cmd))
result = subprocess.run(cmd, cwd=ROOT)
sys.exit(result.returncode)
```

- [ ] **Step 3: Build .exe**

```bash
uv run python build_exe.py
```

Expected: `dist/Pattern.exe` xuất hiện (~80-150 MB). Build log không có lỗi đỏ.

- [ ] **Step 4: Chạy .exe để verify**

```bash
dist\Pattern.exe
```

Expected: cửa sổ mở bình thường, không có console window phụ.

- [ ] **Step 5: Commit**

```bash
git add build_exe.py assets/pattern.ico
git add Pattern.spec   # PyInstaller tạo ra
git commit -m "feat: add build_exe.py + PyInstaller spec"
```

---

## Task 11: Kiểm tra end-to-end

- [ ] **Step 1: Chạy full pipeline qua GUI**

Mở `dist/Pattern.exe` (hoặc `uv run python gui/app.py`):
1. Chọn ngày hôm nay
2. Source: claude-cowork
3. Click "Chạy Pipeline"
4. Xác nhận 3 bước hiện đúng trạng thái
5. Nếu có session → màn hình Review xuất hiện với danh sách skill
6. Chọn 1 skill → "Cài skill đã chọn" → toast thành công
7. Verify `~/.claude/skills/<name>/` tồn tại

- [ ] **Step 2: Kiểm tra edge case — ngày không có session**

Chọn ngày xa trong quá khứ (ví dụ: 2020-01-01) → expected: log "Không có session nào cho ngày này."

- [ ] **Step 3: Verify CLI pipeline vẫn chạy**

```bash
uv run e2e.py --help
uv run python scripts/scan.py --help
uv run python scripts/judge.py --help
uv run python scripts/synth.py --help
```

Expected: tất cả help text bình thường.

- [ ] **Step 4: Chạy toàn bộ test suite**

```bash
uv run pytest -v
```

Expected: tất cả PASS.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Pattern GUI (.exe) — full end-to-end working"
```
