# Pattern MVP — End-to-end Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Lượt 2 (Judge) + Lượt 3 (Synthesis) end-to-end on top of existing `scripts/scan.py`, with a CLI flow that turns session JSONL into a `PROPOSAL.md` + installable skill drafts. Demo-ready by 2026-06-17.

**Architecture:** Two new entry scripts (`scripts/judge.py`, `scripts/synth.py`) compose helpers from `scripts/_lib/` (deterministic aggregator + LLM subprocess wrapper + Jinja2 renderers). LLM calls go through `claude -p` headless. All deterministic logic is TDD-tested with pytest; LLM-touching code is mock-tested for shape + smoke-tested manually.

**Tech Stack:** Python 3.12, pytest, Jinja2, Click, Claude Code CLI (`claude -p`).

**Spec:** `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`

---

## File Structure (decomposition lock-in)

```
scripts/
├── scan.py                     (exists — Lượt 1; not touched)
├── judge.py                    (new — Lượt 2 entry)
├── synth.py                    (new — Lượt 3 entry)
└── _lib/
    ├── __init__.py             (new — empty marker)
    ├── aggregator.py           (new — rule-based clustering, pure Python)
    ├── claude_runner.py        (new — subprocess wrapper, JSON parsing, retry)
    ├── judge_prompts.py        (new — prompt templates as strings)
    ├── render_proposal.py      (new — Jinja2 renderers for both .md files)
    └── synth_templates/
        ├── SKILL.md.j2         (new — fallback Path B template)
        └── golden_tests.md.j2  (new — fallback Path B template)

tests/
├── conftest.py                 (new — sys.path injection + shared fixtures)
├── test_aggregator.py          (new — TDD for clustering + metrics)
├── test_claude_runner.py       (new — mock subprocess, JSON retry)
├── test_render_proposal.py     (new — render with mock candidates)
├── test_accept_template.py     (new — verify generated accept.py copy logic)
└── fixtures/
    └── sessions/               (new — 4 jsonl copied from existing scan output)

pyproject.toml                  (modify — add deps)
.gitignore                      (modify — add data/)
main.py                         (delete)
README.md                       (modify at end — usage steps)
```

**Boundaries:**
- `aggregator.py` knows nothing about LLM or output format — pure data → clusters.
- `claude_runner.py` knows nothing about prompt content — pure subprocess + JSON.
- `judge_prompts.py` is template strings only, no logic.
- `render_proposal.py` is rendering only, takes parsed data in.
- `judge.py` and `synth.py` are wiring; they orchestrate and own CLI surface.

---

## Phase 0 — Setup & cleanup

### Task 1: Add deps + gitignore + remove main.py

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Delete: `main.py`

- [ ] **Step 1: Edit `pyproject.toml`**

Replace the entire file with:

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
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
```

- [ ] **Step 2: Edit `.gitignore`**

Add this block at the end (keep existing content):

```
# Runtime data (sessions, judge output, skill proposals)
data/

# pytest
.pytest_cache/
```

- [ ] **Step 3: Delete `main.py`**

```bash
rm main.py
```

- [ ] **Step 4: Install deps**

```bash
uv sync
```

Expected: deps install, `.venv/` updated. No errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore
git rm main.py
git commit -m "chore: setup deps, gitignore data, remove main.py stub"
```

---

### Task 2: Create folder skeleton

**Files:**
- Create: `scripts/_lib/__init__.py` (empty)
- Create: `scripts/_lib/synth_templates/` (directory)
- Create: `tests/__init__.py` (empty)
- Create: `tests/fixtures/__init__.py` (empty)

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p scripts/_lib/synth_templates
mkdir -p tests/fixtures/sessions
touch scripts/_lib/__init__.py
touch tests/__init__.py
touch tests/fixtures/__init__.py
```

- [ ] **Step 2: Verify structure**

```bash
ls scripts/_lib/
ls tests/
```

Expected output for `scripts/_lib/`: `__init__.py  synth_templates`
Expected output for `tests/`: `__init__.py  fixtures`

- [ ] **Step 3: Commit**

```bash
git add scripts/_lib/__init__.py scripts/_lib/synth_templates tests/__init__.py tests/fixtures
git commit -m "chore: create folder skeleton for _lib and tests"
```

---

### Task 3: Copy session fixtures + write conftest.py

**Files:**
- Copy: `data/sessions_2026-06-12_runAt_20260612-173005/*.jsonl` → `tests/fixtures/sessions/`
- Create: `tests/conftest.py`

- [ ] **Step 1: Copy 4 session JSONL as fixtures**

```bash
cp data/sessions_2026-06-12_runAt_20260612-173005/gifted-adoring-hamilton__802ef332-2f1.jsonl tests/fixtures/sessions/
cp data/sessions_2026-06-12_runAt_20260612-173005/modest-nice-edison__9c3a437a-e29.jsonl tests/fixtures/sessions/
cp data/sessions_2026-06-12_runAt_20260612-173005/relaxed-keen-heisenberg__832450dc-144.jsonl tests/fixtures/sessions/
cp data/sessions_2026-06-12_runAt_20260612-173005/lucid-beautiful-fermat__9de10fe5-9cd.jsonl tests/fixtures/sessions/
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for Pattern tests."""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sessions_dir() -> Path:
    """Directory containing 4 real session JSONL files from 2026-06-12 scan."""
    return FIXTURES_DIR / "sessions"
```

- [ ] **Step 3: Verify fixtures load**

```bash
uv run pytest --collect-only
```

Expected: pytest discovers 0 tests (no tests yet) and finds the `sessions_dir` fixture without import errors.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/fixtures/sessions/
git commit -m "test: add conftest with session fixtures from 2026-06-12 scan"
```

---

## Phase 1 — Aggregator (TDD)

### Task 4: Session loader + dataclasses

**Files:**
- Create: `scripts/_lib/aggregator.py`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing test for `load_sessions`**

Create `tests/test_aggregator.py`:

```python
"""Tests for scripts/_lib/aggregator.py."""

from __future__ import annotations

from pathlib import Path

from _lib.aggregator import Session, load_sessions


def test_load_sessions_reads_all_fixture_files(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    assert len(sessions) == 4
    assert all(isinstance(s, Session) for s in sessions)


def test_load_sessions_extracts_title_and_tools(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    titles = {s.title for s in sessions}
    assert "Computer use capabilities test" in titles
    fermat = next(s for s in sessions if s.process_name == "lucid-beautiful-fermat")
    assert fermat.total_actions > 0
    assert len(fermat.tool_usage) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named '_lib.aggregator'`.

- [ ] **Step 3: Implement minimum to pass**

Create `scripts/_lib/aggregator.py`:

```python
"""Rule-based session clustering for Pattern's Lượt 2 judge stage.

Pure Python. No LLM. Takes per-session JSONL produced by scripts/scan.py and
groups sessions whose behaviour looks similar, so the judge prompt sees small
focused clusters instead of raw noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Session:
    """A flattened view of one session, drawn from its session_summary record."""

    session_id: str
    process_name: str | None
    title: str | None
    intent_seed: str | None
    total_actions: int
    total_user_turns: int
    total_input_tokens: int
    total_output_tokens: int
    duration_seconds: float | None
    tool_usage: dict[str, int]
    retry_count: int
    correction_count: int
    source_file: str = ""


def _read_summary(jsonl_path: Path) -> dict | None:
    with jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("record_type") == "session_summary":
                return rec
    return None


def load_sessions(sessions_dir: Path) -> list[Session]:
    sessions: list[Session] = []
    for jsonl_path in sorted(sessions_dir.glob("*.jsonl")):
        rec = _read_summary(jsonl_path)
        if not rec:
            continue
        sessions.append(Session(
            session_id=rec.get("session_id", jsonl_path.stem),
            process_name=rec.get("process_name"),
            title=rec.get("title"),
            intent_seed=rec.get("intent_seed"),
            total_actions=int(rec.get("total_actions") or 0),
            total_user_turns=int(rec.get("total_user_turns") or 0),
            total_input_tokens=int(rec.get("total_input_tokens") or 0),
            total_output_tokens=int(rec.get("total_output_tokens") or 0),
            duration_seconds=rec.get("duration_seconds"),
            tool_usage=dict(rec.get("tool_usage") or {}),
            retry_count=int(rec.get("retry_count") or 0),
            correction_count=int(rec.get("correction_count") or 0),
            source_file=jsonl_path.name,
        ))
    return sessions
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): add Session dataclass and load_sessions"
```

---

### Task 5: Tool n-gram cluster with Jaccard threshold

**Files:**
- Modify: `scripts/_lib/aggregator.py`
- Modify: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests for `cluster_by_tool_ngram`**

Append to `tests/test_aggregator.py`:

```python
from _lib.aggregator import cluster_by_tool_ngram


def _mk_session(sid: str, tools: dict[str, int], title: str = "x") -> Session:
    return Session(
        session_id=sid, process_name=sid, title=title, intent_seed=None,
        total_actions=sum(tools.values()), total_user_turns=0,
        total_input_tokens=0, total_output_tokens=0, duration_seconds=0.0,
        tool_usage=tools, retry_count=0, correction_count=0,
    )


def test_ngram_groups_sessions_sharing_top3_tools() -> None:
    a = _mk_session("a", {"scan": 5, "edit": 4, "test": 3, "noise": 1})
    b = _mk_session("b", {"scan": 6, "edit": 2, "test": 1})
    c = _mk_session("c", {"send_mail": 3, "calendar": 2, "search": 1})
    clusters = cluster_by_tool_ngram([a, b, c], top_n=3, jaccard_threshold=0.6)
    cluster_sets = [{s.session_id for s in cl} for cl in clusters]
    assert {"a", "b"} in cluster_sets
    assert {"c"} in cluster_sets


def test_ngram_jaccard_below_threshold_splits() -> None:
    # share 1 of 3 → Jaccard = 1/5 = 0.2 → separate clusters
    a = _mk_session("a", {"x": 3, "y": 2, "z": 1})
    b = _mk_session("b", {"x": 3, "p": 2, "q": 1})
    clusters = cluster_by_tool_ngram([a, b], top_n=3, jaccard_threshold=0.6)
    assert len(clusters) == 2


def test_ngram_handles_fewer_than_topn_tools() -> None:
    a = _mk_session("a", {"x": 1})
    b = _mk_session("b", {"x": 1})
    clusters = cluster_by_tool_ngram([a, b], top_n=3, jaccard_threshold=0.6)
    assert len(clusters) == 1
    assert {s.session_id for s in clusters[0]} == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 3 new tests FAIL with `ImportError: cannot import name 'cluster_by_tool_ngram'`.

- [ ] **Step 3: Implement `cluster_by_tool_ngram`**

Append to `scripts/_lib/aggregator.py`:

```python
def _top_n_tools(session: Session, n: int) -> frozenset[str]:
    sorted_tools = sorted(
        session.tool_usage.items(), key=lambda kv: (-kv[1], kv[0])
    )
    return frozenset(name for name, _ in sorted_tools[:n])


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cluster_by_tool_ngram(
    sessions: Iterable[Session],
    *,
    top_n: int = 3,
    jaccard_threshold: float = 0.6,
) -> list[list[Session]]:
    """Greedy single-pass clustering by overlap of each session's top-N tools.

    Each session is added to the first existing cluster whose representative
    set has Jaccard >= threshold; otherwise it starts a new cluster.
    """
    clusters: list[list[Session]] = []
    cluster_keys: list[frozenset[str]] = []
    for session in sessions:
        key = _top_n_tools(session, top_n)
        placed = False
        for idx, repr_key in enumerate(cluster_keys):
            if _jaccard(key, repr_key) >= jaccard_threshold:
                clusters[idx].append(session)
                cluster_keys[idx] = repr_key | key  # union as representative
                placed = True
                break
        if not placed:
            clusters.append([session])
            cluster_keys.append(key)
    return clusters
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): cluster_by_tool_ngram with Jaccard threshold"
```

---

### Task 6: Title sub-grouping + filter

**Files:**
- Modify: `scripts/_lib/aggregator.py`
- Modify: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_aggregator.py`:

```python
from _lib.aggregator import subcluster_by_title, filter_by_size


def test_subcluster_groups_similar_titles() -> None:
    a = _mk_session("a", {"x": 1}, title="Tóm tắt file PDF báo cáo")
    b = _mk_session("b", {"x": 1}, title="tóm tắt file PDF tài liệu!")
    c = _mk_session("c", {"x": 1}, title="Review code Python module utils")
    result = subcluster_by_title([a, b, c], jaccard_threshold=0.5)
    title_groups = [{s.session_id for s in g} for g in result]
    assert {"a", "b"} in title_groups
    assert {"c"} in title_groups


def test_subcluster_handles_missing_title() -> None:
    a = _mk_session("a", {"x": 1}, title=None)  # type: ignore[arg-type]
    b = _mk_session("b", {"x": 1}, title=None)  # type: ignore[arg-type]
    result = subcluster_by_title([a, b], jaccard_threshold=0.5)
    assert len(result) == 2  # missing titles never group


def test_filter_by_size_drops_below_threshold() -> None:
    g1 = [_mk_session("a", {}), _mk_session("b", {})]
    g2 = [_mk_session("c", {})]
    result = filter_by_size([g1, g2], min_size=2)
    assert result == [g1]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 3 new tests FAIL on imports.

- [ ] **Step 3: Implement**

Append to `scripts/_lib/aggregator.py`:

```python
import re
import unicodedata


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_title(title: str | None) -> frozenset[str]:
    if not title:
        return frozenset()
    folded = unicodedata.normalize("NFC", title).lower()
    stripped = _PUNCT_RE.sub(" ", folded)
    tokens = [t for t in stripped.split() if len(t) >= 2]
    return frozenset(tokens)


def subcluster_by_title(
    sessions: Iterable[Session],
    *,
    jaccard_threshold: float = 0.5,
) -> list[list[Session]]:
    """Sub-cluster by title token Jaccard. Sessions with missing/empty titles
    are never grouped together (defensive: avoid false positives)."""
    groups: list[list[Session]] = []
    keys: list[frozenset[str]] = []
    for session in sessions:
        key = _normalize_title(session.title)
        if not key:
            groups.append([session])
            keys.append(key)
            continue
        placed = False
        for idx, repr_key in enumerate(keys):
            if repr_key and _jaccard(key, repr_key) >= jaccard_threshold:
                groups[idx].append(session)
                keys[idx] = repr_key | key
                placed = True
                break
        if not placed:
            groups.append([session])
            keys.append(key)
    return groups


def filter_by_size(
    clusters: Iterable[list[Session]], *, min_size: int
) -> list[list[Session]]:
    return [c for c in clusters if len(c) >= min_size]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): title sub-cluster and size filter"
```

---

### Task 7: Cluster metrics + top-level `aggregate()` API

**Files:**
- Modify: `scripts/_lib/aggregator.py`
- Modify: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_aggregator.py`:

```python
from _lib.aggregator import Cluster, aggregate


def test_aggregate_returns_clusters_with_metrics(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    clusters = aggregate(sessions, min_size=1)  # min_size=1 so 4 fixtures show up
    assert all(isinstance(c, Cluster) for c in clusters)
    assert all(c.recurrence >= 1 for c in clusters)
    # at least one cluster contains the high-retry fermat session
    fermat_in = any(
        any(s.process_name == "lucid-beautiful-fermat" for s in c.sessions)
        for c in clusters
    )
    assert fermat_in


def test_aggregate_metrics_classify_inefficient() -> None:
    high_retry = _mk_session(
        "h", {"click": 14}, title="Computer test",
    )
    high_retry = Session(
        session_id="h", process_name="h", title="Computer test", intent_seed=None,
        total_actions=14, total_user_turns=5, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=10.0,
        tool_usage={"click": 14}, retry_count=13, correction_count=0,
    )
    other = Session(
        session_id="h2", process_name="h2", title="Computer test", intent_seed=None,
        total_actions=10, total_user_turns=5, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=10.0,
        tool_usage={"click": 10}, retry_count=8, correction_count=0,
    )
    clusters = aggregate([high_retry, other], min_size=2)
    assert len(clusters) == 1
    assert clusters[0].behavior_class_hint == "inefficient"
    assert clusters[0].retry_rate > 0.2


def test_aggregate_filters_singletons_by_default(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    clusters = aggregate(sessions, min_size=2)
    # 4 fixtures with very different titles → likely 0 clusters of size >= 2
    assert all(c.recurrence >= 2 for c in clusters)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 3 new tests FAIL on imports.

- [ ] **Step 3: Implement**

Append to `scripts/_lib/aggregator.py`:

```python
@dataclass
class Cluster:
    sessions: list[Session]
    representative_tools: list[str]
    representative_titles: list[str]
    recurrence: int
    retry_rate: float
    correction_rate: float
    avg_duration_seconds: float
    total_tokens: int
    behavior_class_hint: str  # "process" | "inefficient" | "unclear"

    def to_dict(self) -> dict:
        return {
            "session_ids": [s.session_id for s in self.sessions],
            "process_names": [s.process_name for s in self.sessions],
            "source_files": [s.source_file for s in self.sessions],
            "representative_tools": self.representative_tools,
            "representative_titles": self.representative_titles,
            "recurrence": self.recurrence,
            "retry_rate": round(self.retry_rate, 3),
            "correction_rate": round(self.correction_rate, 3),
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "total_tokens": self.total_tokens,
            "behavior_class_hint": self.behavior_class_hint,
            "top_tools_per_session": [
                dict(sorted(s.tool_usage.items(), key=lambda kv: -kv[1])[:5])
                for s in self.sessions
            ],
            "titles": [s.title for s in self.sessions],
        }


def _classify(retry_rate: float, recurrence: int) -> str:
    if retry_rate >= 0.2:
        return "inefficient"
    if retry_rate < 0.1 and recurrence >= 3:
        return "process"
    return "unclear"


def _build_cluster(group: list[Session]) -> Cluster:
    n = len(group)
    retry_rate = (
        sum(s.retry_count / s.total_actions for s in group if s.total_actions)
        / max(1, sum(1 for s in group if s.total_actions))
    )
    correction_rate = (
        sum(s.correction_count / s.total_user_turns for s in group if s.total_user_turns)
        / max(1, sum(1 for s in group if s.total_user_turns))
    )
    avg_duration = sum((s.duration_seconds or 0.0) for s in group) / n
    total_tokens = sum(s.total_input_tokens + s.total_output_tokens for s in group)
    # Representative tools = union of top-3 across the group
    rep_tools: set[str] = set()
    for s in group:
        rep_tools |= _top_n_tools(s, 3)
    return Cluster(
        sessions=group,
        representative_tools=sorted(rep_tools),
        representative_titles=[s.title for s in group if s.title],
        recurrence=n,
        retry_rate=retry_rate,
        correction_rate=correction_rate,
        avg_duration_seconds=avg_duration,
        total_tokens=total_tokens,
        behavior_class_hint=_classify(retry_rate, n),
    )


def aggregate(
    sessions: list[Session],
    *,
    min_size: int = 2,
    top_n: int = 3,
    tool_threshold: float = 0.6,
    title_threshold: float = 0.5,
) -> list[Cluster]:
    """End-to-end clustering pipeline: tool ngram → title sub-cluster → filter → metrics."""
    tool_clusters = cluster_by_tool_ngram(
        sessions, top_n=top_n, jaccard_threshold=tool_threshold
    )
    refined: list[list[Session]] = []
    for tc in tool_clusters:
        refined.extend(subcluster_by_title(tc, jaccard_threshold=title_threshold))
    sized = filter_by_size(refined, min_size=min_size)
    return [_build_cluster(g) for g in sized]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_aggregator.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): Cluster metrics and end-to-end aggregate()"
```

---

## Phase 2 — Claude runner (TDD with mock)

### Task 8: `claude_runner.run()` with timeout + JSON extraction

**Files:**
- Create: `scripts/_lib/claude_runner.py`
- Create: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_claude_runner.py`:

```python
"""Tests for scripts/_lib/claude_runner.py."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from _lib.claude_runner import (
    ClaudeRunError,
    extract_json_block,
    run_claude,
    run_claude_json,
)


def test_extract_json_block_finds_array_in_prose() -> None:
    raw = "Here is the result:\n```json\n[{\"name\": \"x\"}]\n```\nDone."
    assert extract_json_block(raw) == '[{"name": "x"}]'


def test_extract_json_block_finds_bare_object() -> None:
    raw = "{\"key\": 1}"
    assert extract_json_block(raw) == '{"key": 1}'


def test_extract_json_block_raises_when_no_json() -> None:
    with pytest.raises(ValueError):
        extract_json_block("no json here at all")


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_returns_stdout(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="hello", stderr=""
    )
    assert run_claude("prompt", timeout=10) == "hello"
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0] == "claude"
    assert args[0][1] == "-p"
    assert kwargs["timeout"] == 10


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_raises_on_nonzero_exit(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="boom"
    )
    with pytest.raises(ClaudeRunError, match="boom"):
        run_claude("prompt", timeout=10)


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_parses_clean_output(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='[{"a": 1}]', stderr=""
    )
    assert run_claude_json("prompt") == [{"a": 1}]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_claude_runner.py -v
```

Expected: all FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `claude_runner.py`**

Create `scripts/_lib/claude_runner.py`:

```python
"""Thin wrapper around `claude -p` headless calls.

Owns:
- subprocess invocation with timeout
- non-zero exit detection
- best-effort JSON block extraction from prose-padded output
- one self-heal retry when JSON parsing fails

Does NOT own prompt content (see judge_prompts.py).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any


CLAUDE_BIN = "claude"


class ClaudeRunError(RuntimeError):
    """Raised when `claude -p` exits non-zero or output cannot be parsed."""


_FENCED_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


def extract_json_block(raw: str) -> str:
    """Return the first JSON array or object embedded in `raw`.

    Tolerates fenced ```json blocks, surrounding prose, and trailing notes.
    Raises ValueError if no JSON-looking region is found.
    """
    fenced = _FENCED_RE.search(raw)
    if fenced:
        candidate = fenced.group(1).strip()
        if candidate and candidate[0] in "[{":
            return candidate
    # Fall back: find first [ or { and balance brackets.
    start = -1
    for i, ch in enumerate(raw):
        if ch in "[{":
            start = i
            break
    if start < 0:
        raise ValueError("no JSON array or object found in output")
    opener = raw[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    raise ValueError("unbalanced JSON brackets in output")


def run_claude(prompt: str, *, timeout: float = 180.0) -> str:
    """Invoke `claude -p <prompt>` and return stdout. Raises on non-zero exit."""
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeRunError(f"claude -p timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ClaudeRunError(f"claude CLI not found on PATH ({CLAUDE_BIN})") from e
    if result.returncode != 0:
        raise ClaudeRunError(
            f"claude -p exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def run_claude_json(prompt: str, *, timeout: float = 180.0) -> Any:
    """Run prompt and parse the output as JSON. One self-heal retry on parse fail."""
    raw = run_claude(prompt, timeout=timeout)
    try:
        return json.loads(extract_json_block(raw))
    except (json.JSONDecodeError, ValueError) as first_err:
        repair_prompt = (
            "Fix the following so it is a single JSON value (array or object) "
            "with no prose. Output JSON only.\n\n"
            f"PARSE_ERROR: {first_err}\n\nORIGINAL:\n{raw}"
        )
        raw2 = run_claude(repair_prompt, timeout=min(60.0, timeout))
        return json.loads(extract_json_block(raw2))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_claude_runner.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/claude_runner.py tests/test_claude_runner.py
git commit -m "feat(runner): claude -p wrapper with JSON extraction"
```

---

### Task 9: Test the self-heal retry path

**Files:**
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests for retry**

Append to `tests/test_claude_runner.py`:

```python
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_retries_when_first_output_is_garbage(mock_run) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="here's the thing without json", stderr="",
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout='[{"a": 1}]', stderr="",
        ),
    ]
    assert run_claude_json("prompt") == [{"a": 1}]
    assert mock_run.call_count == 2


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_propagates_second_failure(mock_run) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="garbage 1", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="garbage 2", stderr=""
        ),
    ]
    with pytest.raises((json.JSONDecodeError, ValueError)):
        run_claude_json("prompt")
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/test_claude_runner.py -v
```

Expected: 8 passed (retry behaviour already implemented in Task 8).

- [ ] **Step 3: Commit**

```bash
git add tests/test_claude_runner.py
git commit -m "test(runner): cover JSON self-heal retry path"
```

---

## Phase 3 — Judge wiring

### Task 10: Judge prompt template

**Files:**
- Create: `scripts/_lib/judge_prompts.py`

- [ ] **Step 1: Create the prompt file**

Create `scripts/_lib/judge_prompts.py`:

```python
"""Prompt strings for Pattern's Lượt 2 judge call.

Kept in one place so the prompt is reviewable as a diff without code noise.
"""

from __future__ import annotations

import json
from typing import Any


JUDGE_SYSTEM = """Bạn là judge phân tích pattern hành vi user trên Claude Cowork.
Focus 2 hành vi: PROCESS_ORCHESTRATION + INEFFICIENT_RETRY.
Tham chiếu schema 7 lớp ở docs/agent_responce/data_goal.md."""


JUDGE_INSTRUCTIONS = """Với mỗi cluster dưới đây, hãy:
1. Xác định behavior_class ∈ {process, inefficient, not_a_pattern}
2. Đặt tên pattern (snake_case, <= 30 ký tự, không trùng installed_skills)
3. Mô tả trigger_intent song ngữ Việt-Anh (khi nào dùng skill này)
4. Trích action_template (chuỗi tool + input shape ngắn gọn)
5. Score: recurrence (1-5), cohesion (1-5), personalization (1-5)
6. Risk flags từ tập: write_action, deletes_files, external_api, sends_message

CRITIQUE INLINE (tự đóng cả vai critique trước khi output):
- Trùng tên hoặc trùng intent với installed_skills => loại
- Tổng score < 9 => loại
- Cluster size < 2 => loại
- Pattern quá generic (ví dụ "file_edit", "ask_question") => loại

Mỗi candidate bị loại vẫn có trong output với rejected_reason set; những cluster
là not_a_pattern thì rejected_reason = "not_a_pattern".

Output STRICT JSON array; schema mỗi phần tử:
{
  "name": "...",
  "trigger_intent": {"vi": "...", "en": "..."},
  "action_template": [{"tool": "...", "input_shape": "..."}],
  "evidence": {"session_ids": [...], "process_names": [...]},
  "score": {"recurrence": 1-5, "cohesion": 1-5, "personalization": 1-5},
  "behavior_class": "process" | "inefficient" | "not_a_pattern",
  "risk_flags": [...],
  "rejected_reason": null | "duplicate" | "low_score" | "low_recurrence" | "too_generic" | "not_a_pattern"
}
KHÔNG kèm prose ngoài JSON."""


def build_judge_prompt(
    clusters: list[dict[str, Any]],
    installed_skills: list[str],
) -> str:
    payload = {
        "clusters": clusters,
        "installed_skills": installed_skills,
    }
    return (
        f"{JUDGE_SYSTEM}\n\n{JUDGE_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
```

- [ ] **Step 2: Verify module imports**

```bash
uv run python -c "from _lib.judge_prompts import build_judge_prompt; print(build_judge_prompt([{'recurrence': 2}], ['x'])[:200])"
```

Expected: prints first 200 chars of prompt without errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/_lib/judge_prompts.py
git commit -m "feat(judge): prompt template with inline critique rules"
```

---

### Task 11: Render `pattern_report.md`

**Files:**
- Create: `scripts/_lib/render_proposal.py`
- Create: `tests/test_render_proposal.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_render_proposal.py`:

```python
"""Tests for scripts/_lib/render_proposal.py."""

from __future__ import annotations

from _lib.render_proposal import render_pattern_report


def test_pattern_report_lists_candidates_and_clusters() -> None:
    clusters = [
        {
            "session_ids": ["s1", "s2"],
            "process_names": ["proc-a", "proc-b"],
            "representative_tools": ["scan", "edit"],
            "representative_titles": ["Tóm tắt file PDF báo cáo"],
            "recurrence": 2,
            "retry_rate": 0.0,
            "correction_rate": 0.0,
            "avg_duration_seconds": 12.3,
            "total_tokens": 1000,
            "behavior_class_hint": "process",
            "top_tools_per_session": [{"scan": 5}, {"edit": 4}],
            "titles": ["Tóm tắt file PDF báo cáo", "Tóm tắt file PDF tài liệu"],
        }
    ]
    candidates = [
        {
            "name": "summarize_pdf",
            "trigger_intent": {"vi": "Khi user muốn tóm tắt PDF", "en": "When user wants to summarize PDF"},
            "action_template": [{"tool": "scan", "input_shape": "path"}],
            "evidence": {"session_ids": ["s1", "s2"], "process_names": ["proc-a"]},
            "score": {"recurrence": 4, "cohesion": 4, "personalization": 3},
            "behavior_class": "process",
            "risk_flags": [],
            "rejected_reason": None,
        }
    ]
    md = render_pattern_report(
        date="2026-06-13",
        date_range="2026-06-13..2026-06-13",
        sessions_scanned=4,
        clusters=clusters,
        candidates=candidates,
    )
    assert "summarize_pdf" in md
    assert "process" in md
    assert "Khi user muốn tóm tắt PDF" in md
    assert "2026-06-13" in md
    # Rejected candidates should not appear in the "Top candidates" section,
    # but accepted candidates should.
    assert "## Top candidates" in md or "## Candidates" in md
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_render_proposal.py -v
```

Expected: FAIL on import.

- [ ] **Step 3: Implement renderer**

Create `scripts/_lib/render_proposal.py`:

```python
"""Jinja2 renderers for Lượt 2 pattern_report.md and Lượt 3 PROPOSAL.md."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment


_env = Environment(
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


_PATTERN_REPORT_TMPL = _env.from_string("""\
# Pattern report — {{ date }}

| Field | Value |
| --- | --- |
| Date range | {{ date_range }} |
| Sessions scanned | {{ sessions_scanned }} |
| Clusters found | {{ clusters | length }} |
| Candidates emitted | {{ candidates | length }} |
| Candidates passed critique | {{ accepted | length }} |

## Clusters

{% for cl in clusters %}
### Cluster {{ loop.index }} ({{ cl.behavior_class_hint }})
- recurrence: {{ cl.recurrence }}, retry_rate: {{ cl.retry_rate }}, correction_rate: {{ cl.correction_rate }}
- representative tools: `{{ cl.representative_tools | join(", ") }}`
- titles: {{ cl.titles | join(" | ") }}
- sessions: {{ cl.process_names | join(", ") }}

{% endfor %}

## Top candidates (passed critique)

{% if accepted %}
{% for c in accepted %}
### {{ loop.index }}. `{{ c.name }}` — {{ c.behavior_class }}
- Trigger (VI): {{ c.trigger_intent.vi }}
- Trigger (EN): {{ c.trigger_intent.en }}
- Score: recurrence={{ c.score.recurrence }}, cohesion={{ c.score.cohesion }}, personalization={{ c.score.personalization }} (total {{ c.score.recurrence + c.score.cohesion + c.score.personalization }})
- Action template:
{% for step in c.action_template %}
  - `{{ step.tool }}` ← {{ step.input_shape }}
{% endfor %}
- Evidence sessions: {{ c.evidence.session_ids | join(", ") }}
- Risk flags: {{ c.risk_flags | join(", ") if c.risk_flags else "none" }}

{% endfor %}
{% else %}
_No candidates passed critique._
{% endif %}

## Rejected candidates

{% if rejected %}
{% for c in rejected %}
- `{{ c.name }}` — {{ c.rejected_reason }}
{% endfor %}
{% else %}
_None._
{% endif %}
""")


def render_pattern_report(
    *,
    date: str,
    date_range: str,
    sessions_scanned: int,
    clusters: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str:
    accepted = [c for c in candidates if not c.get("rejected_reason")]
    rejected = [c for c in candidates if c.get("rejected_reason")]
    return _PATTERN_REPORT_TMPL.render(
        date=date,
        date_range=date_range,
        sessions_scanned=sessions_scanned,
        clusters=clusters,
        candidates=candidates,
        accepted=accepted,
        rejected=rejected,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_render_proposal.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/render_proposal.py tests/test_render_proposal.py
git commit -m "feat(report): render_pattern_report Jinja2 template"
```

---

### Task 12: `scripts/judge.py` entry point

**Files:**
- Create: `scripts/judge.py`

- [ ] **Step 1: Implement entry script**

Create `scripts/judge.py`:

```python
"""Lượt 2 — LLM-as-judge: aggregate sessions → cluster → call Claude → candidates.

Usage:
    python scripts/judge.py \\
        --sessions-dir data/sessions_2026-06-13_runAt_<runTs> \\
        [--installed-skills-dir ~/.claude/skills] \\
        [--min-size 2] [--top-candidates 5]

Outputs to data/judge_<date>/{cluster_summary.json, pattern_report.md,
candidate_skills.json, _raw_judge_output.txt}.
"""

from __future__ import annotations

import json
import sys
from datetime import date as _date
from pathlib import Path

import click

# Allow `from _lib.* import ...` when run as `python scripts/judge.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.aggregator import aggregate, load_sessions  # noqa: E402
from _lib.claude_runner import ClaudeRunError, run_claude, run_claude_json  # noqa: E402
from _lib.judge_prompts import build_judge_prompt  # noqa: E402
from _lib.render_proposal import render_pattern_report  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"


def _list_installed_skills(skills_dir: Path) -> list[str]:
    if not skills_dir.exists():
        return []
    return sorted(p.name for p in skills_dir.iterdir() if p.is_dir())


@click.command()
@click.option(
    "--sessions-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory of session JSONL produced by scan.py",
)
@click.option(
    "--installed-skills-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.home() / ".claude" / "skills",
    show_default=True,
)
@click.option("--min-size", type=int, default=2, show_default=True)
@click.option("--top-candidates", type=int, default=5, show_default=True)
@click.option("--timeout", type=float, default=180.0, show_default=True)
def main(
    sessions_dir: Path,
    installed_skills_dir: Path,
    min_size: int,
    top_candidates: int,
    timeout: float,
) -> None:
    today = _date.today().isoformat()
    out_dir = DATA_ROOT / f"judge_{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"[judge] loading sessions from {sessions_dir}")
    sessions = load_sessions(sessions_dir)
    click.echo(f"[judge] loaded {len(sessions)} sessions")

    clusters = aggregate(sessions, min_size=min_size)
    cluster_dicts = [c.to_dict() for c in clusters]
    (out_dir / "cluster_summary.json").write_text(
        json.dumps(cluster_dicts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    click.echo(f"[judge] {len(clusters)} clusters after filter (min_size={min_size})")

    if not clusters:
        click.echo("[judge] no clusters → skipping LLM judge")
        candidates: list[dict] = []
    else:
        installed = _list_installed_skills(installed_skills_dir)
        prompt = build_judge_prompt(cluster_dicts, installed)
        click.echo(f"[judge] calling `claude -p` (timeout={timeout}s)")
        try:
            raw = run_claude(prompt, timeout=timeout)
            (out_dir / "_raw_judge_output.txt").write_text(raw, encoding="utf-8")
            from _lib.claude_runner import extract_json_block
            candidates = json.loads(extract_json_block(raw))
            if not isinstance(candidates, list):
                raise ValueError("expected JSON array at top level")
        except (ClaudeRunError, ValueError, json.JSONDecodeError) as e:
            click.echo(f"[judge] first parse failed: {e}; retrying via self-heal")
            candidates = run_claude_json(prompt, timeout=timeout)

    accepted = [c for c in candidates if not c.get("rejected_reason")]
    accepted = sorted(
        accepted,
        key=lambda c: sum(c.get("score", {}).values()),
        reverse=True,
    )[:top_candidates]
    final = accepted + [c for c in candidates if c.get("rejected_reason")]
    (out_dir / "candidate_skills.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_md = render_pattern_report(
        date=today,
        date_range=str(sessions_dir.name),
        sessions_scanned=len(sessions),
        clusters=cluster_dicts,
        candidates=final,
    )
    (out_dir / "pattern_report.md").write_text(report_md, encoding="utf-8")

    click.echo(
        f"[judge] done. {len(accepted)} accepted, "
        f"{len(final) - len(accepted)} rejected → {out_dir}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test against fixtures (no LLM)**

Create a 1-cluster scenario manually to verify wiring without calling Claude:

```bash
uv run python -c "
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from _lib.aggregator import aggregate, load_sessions
sessions = load_sessions(Path('tests/fixtures/sessions'))
clusters = aggregate(sessions, min_size=1)
print(f'loaded {len(sessions)} sessions, {len(clusters)} clusters')
print(clusters[0].to_dict() if clusters else 'no clusters')
"
```

Expected: prints `loaded 4 sessions, N clusters` (N ≥ 1) and the first cluster's dict.

- [ ] **Step 3: Commit**

```bash
git add scripts/judge.py
git commit -m "feat: scripts/judge.py end-to-end Lượt 2 wiring"
```

---

## Phase 4 — Synthesis

### Task 13: Path B template files

**Files:**
- Create: `scripts/_lib/synth_templates/SKILL.md.j2`
- Create: `scripts/_lib/synth_templates/golden_tests.md.j2`

- [ ] **Step 1: Create `SKILL.md.j2`**

Create `scripts/_lib/synth_templates/SKILL.md.j2`:

```jinja
---
name: {{ name }}
description: |
  VI: {{ trigger_vi }}
  EN: {{ trigger_en }}
behavior_class: {{ behavior_class }}
generated_by: pattern-mvp
generated_on: {{ generated_on }}
risk_flags: [{{ risk_flags | join(", ") }}]
---

# {{ name }}

## Khi nào dùng / When to use

- **VI:** {{ trigger_vi }}
- **EN:** {{ trigger_en }}

## Các bước / Steps

{{ steps_markdown }}

## Evidence

Skill được rút từ các session sau (xem `data/sessions_*/`):

{% for sid in evidence_session_ids %}
- `{{ sid }}`
{% endfor %}

## Risk flags

{% if risk_flags %}
{% for flag in risk_flags %}
- `{{ flag }}`
{% endfor %}
{% else %}
_None._
{% endif %}
```

- [ ] **Step 2: Create `golden_tests.md.j2`**

Create `scripts/_lib/synth_templates/golden_tests.md.j2`:

```jinja
# Golden tests — {{ name }}

3 sample queries built from evidence. Run them manually in Claude Cowork
and verify the skill triggers + the output meets expectation.

## Test 1

**Query:**
{{ golden_test_1.query }}

**Expected:**
{{ golden_test_1.expected }}

## Test 2

**Query:**
{{ golden_test_2.query }}

**Expected:**
{{ golden_test_2.expected }}

## Test 3

**Query:**
{{ golden_test_3.query }}

**Expected:**
{{ golden_test_3.expected }}
```

- [ ] **Step 3: Verify templates parse**

```bash
uv run python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('scripts/_lib/synth_templates'))
env.get_template('SKILL.md.j2')
env.get_template('golden_tests.md.j2')
print('ok')
"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add scripts/_lib/synth_templates/SKILL.md.j2 scripts/_lib/synth_templates/golden_tests.md.j2
git commit -m "feat(synth): Jinja2 templates for Path B fallback skill drafts"
```

---

### Task 14: Synth Path B template-fill function (testable)

**Files:**
- Modify: `scripts/_lib/render_proposal.py`
- Modify: `tests/test_render_proposal.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render_proposal.py`:

```python
from pathlib import Path

from _lib.render_proposal import render_skill_dir


def test_render_skill_dir_writes_skill_and_golden_tests(tmp_path: Path) -> None:
    candidate = {
        "name": "summarize_pdf",
        "trigger_intent": {"vi": "khi cần tóm tắt PDF", "en": "when summarizing PDF"},
        "behavior_class": "process",
        "risk_flags": [],
        "evidence": {"session_ids": ["s1", "s2"]},
    }
    filled = {
        "steps_markdown": "1. read file\n2. summarize\n3. return summary",
        "golden_test_1": {"query": "Q1", "expected": "E1"},
        "golden_test_2": {"query": "Q2", "expected": "E2"},
        "golden_test_3": {"query": "Q3", "expected": "E3"},
    }
    out = render_skill_dir(
        candidate=candidate, filled=filled,
        output_dir=tmp_path, generated_on="2026-06-13",
    )
    skill_md = (out / "SKILL.md").read_text(encoding="utf-8")
    golden = (out / "golden_tests.md").read_text(encoding="utf-8")
    assert "summarize_pdf" in skill_md
    assert "khi cần tóm tắt PDF" in skill_md
    assert "1. read file" in skill_md
    assert "Q1" in golden and "E2" in golden
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_render_proposal.py -v
```

Expected: new test FAILS on import.

- [ ] **Step 3: Implement `render_skill_dir`**

Append to `scripts/_lib/render_proposal.py`:

```python
from pathlib import Path

from jinja2 import FileSystemLoader


_TEMPLATES_DIR = Path(__file__).parent / "synth_templates"
_file_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_skill_dir(
    *,
    candidate: dict[str, Any],
    filled: dict[str, Any],
    output_dir: Path,
    generated_on: str,
) -> Path:
    """Render Path B fallback skill folder: SKILL.md + golden_tests.md.

    `candidate` is one element from candidate_skills.json; `filled` is the LLM
    template-fill output (steps + 3 golden tests).
    """
    skill_dir = output_dir / candidate["name"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "name": candidate["name"],
        "trigger_vi": candidate["trigger_intent"]["vi"],
        "trigger_en": candidate["trigger_intent"]["en"],
        "behavior_class": candidate.get("behavior_class", "process"),
        "risk_flags": candidate.get("risk_flags") or [],
        "evidence_session_ids": candidate.get("evidence", {}).get("session_ids", []),
        "generated_on": generated_on,
        "steps_markdown": filled["steps_markdown"],
        "golden_test_1": filled["golden_test_1"],
        "golden_test_2": filled["golden_test_2"],
        "golden_test_3": filled["golden_test_3"],
    }
    (skill_dir / "SKILL.md").write_text(
        _file_env.get_template("SKILL.md.j2").render(**ctx), encoding="utf-8"
    )
    (skill_dir / "golden_tests.md").write_text(
        _file_env.get_template("golden_tests.md.j2").render(**ctx), encoding="utf-8"
    )
    return skill_dir
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_render_proposal.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/render_proposal.py tests/test_render_proposal.py
git commit -m "feat(synth): render_skill_dir for Path B template fill"
```

---

### Task 15: `scripts/synth.py` — Path A with Path B fallback

**Files:**
- Create: `scripts/synth.py`

- [ ] **Step 1: Implement entry script**

Create `scripts/synth.py`:

```python
"""Lượt 3 — Skill synthesis with skill-creator headless + template fallback.

Usage:
    python scripts/synth.py --candidates data/judge_<date>/candidate_skills.json \\
        [--top 3] [--timeout 120]

For each top-N accepted candidate:
- Path A: ask `claude -p` to use the skill-creator skill, output to a per-skill
  folder. If SKILL.md exists after the call, mark synth_path = "A".
- Path B: if A fails (timeout or no file), fall back to a smaller `claude -p`
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
from _lib.render_proposal import render_skill_dir  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent


def _path_a_prompt(candidate: dict, skill_dir: Path) -> str:
    return f"""Use the skill-creator skill. Create a new skill with these inputs.

NAME: {candidate['name']}
TRIGGER (VI): {candidate['trigger_intent']['vi']}
TRIGGER (EN): {candidate['trigger_intent']['en']}
BEHAVIOR_CLASS: {candidate.get('behavior_class', 'process')}
ACTION_SEQUENCE_JSON: {json.dumps(candidate.get('action_template', []), ensure_ascii=False)}
EVIDENCE_SESSION_IDS: {", ".join(candidate.get('evidence', {}).get('session_ids', []))}
RISK_FLAGS: {", ".join(candidate.get('risk_flags', []))}

OUTPUT FOLDER (absolute): {skill_dir}

Requirements:
- Write SKILL.md with frontmatter (name, description bilingual VI/EN).
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
    print(f"  + installed {{name}} → {{dst}}")


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
    print("Pattern — skill proposal")
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
    skill_dir = out_dir / candidate["name"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    today = _date.today().isoformat()

    try:
        run_claude(_path_a_prompt(candidate, skill_dir), timeout=timeout)
    except ClaudeRunError as e:
        click.echo(f"  ! Path A failed for {candidate['name']}: {e}")
    if (skill_dir / "SKILL.md").exists():
        return "A"

    click.echo(f"  ↳ falling back to Path B for {candidate['name']}")
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
        click.echo(f"[synth] → {c['name']}")
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
    click.echo(f"[synth] done → {out_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify entry imports**

```bash
uv run python -c "import sys; sys.path.insert(0, 'scripts'); import synth; print(synth.main.name)"
```

Expected: prints `main`.

- [ ] **Step 3: Commit**

```bash
git add scripts/synth.py
git commit -m "feat: scripts/synth.py with Path A + Path B fallback"
```

---

### Task 16: Test the emitted `accept.py`

**Files:**
- Create: `tests/test_accept_template.py`

- [ ] **Step 1: Write the test**

Create `tests/test_accept_template.py`:

```python
"""Verify the accept.py emitted by synth.py behaves correctly."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from synth import _emit_accept_py


def test_emitted_accept_installs_via_argv(tmp_path: Path) -> None:
    # Arrange: fake proposal dir with one candidate folder
    proposal = tmp_path / "proposal"
    proposal.mkdir()
    skill_src = proposal / "summarize_pdf"
    skill_src.mkdir()
    (skill_src / "SKILL.md").write_text("hello", encoding="utf-8")
    _emit_accept_py(proposal, ["summarize_pdf"])

    fake_home = tmp_path / "home"
    # Inherit env so Python subprocess starts on Windows (needs SystemRoot
    # etc.), then override HOME/USERPROFILE so Path.home() resolves to the
    # temp dir. Cross-platform: HOME on POSIX, USERPROFILE on Windows.
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    result = subprocess.run(
        [sys.executable, str(proposal / "accept.py"), "1"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    installed = fake_home / ".claude" / "skills" / "summarize_pdf" / "SKILL.md"
    assert installed.exists()
    assert installed.read_text(encoding="utf-8") == "hello"
```

Need a conftest entry so pytest can import `synth`:

- [ ] **Step 2: Update `tests/conftest.py`**

Replace `tests/conftest.py` contents with:

```python
"""Shared pytest fixtures for Pattern tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Make scripts/ importable for tests that hit judge.py / synth.py helpers.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def sessions_dir() -> Path:
    """Directory containing 4 real session JSONL files from 2026-06-12 scan."""
    return FIXTURES_DIR / "sessions"
```

- [ ] **Step 3: Run test to verify it passes**

```bash
uv run pytest tests/test_accept_template.py -v
```

Expected: 1 passed (no Claude call needed).

- [ ] **Step 4: Commit**

```bash
git add tests/test_accept_template.py tests/conftest.py
git commit -m "test: verify emitted accept.py installs skill into HOME/.claude/skills"
```

---

## Phase 5 — Polish

### Task 17: Update README with the 3-step usage

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write README**

Replace `README.md` contents with:

```markdown
# Pattern — Behavior → Skill harness for Claude Cowork (MVP)

Quan sát hành vi user trên Claude Cowork → đề xuất Skill draft cá nhân hoá.
Spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`.

## Yêu cầu

- Python 3.12+, `uv`
- Claude Code CLI có sẵn trên `PATH` (`claude` binary)
- Đã có session log Claude Cowork trên máy

## Cài đặt

```bash
uv sync
```

## Pipeline 3 bước

### 1) Scan — trích session JSONL từ log Claude Desktop

```bash
uv run python scripts/scan.py
```

Mặc định scan ngày hôm nay; xem `TARGET_DATE` trong `scripts/scan.py` để đổi.
Output: `data/sessions_<date>_runAt_<runTs>/`.

### 2) Judge — cluster + LLM-as-judge → candidate skills

```bash
uv run python scripts/judge.py \
    --sessions-dir data/sessions_<date>_runAt_<runTs> \
    --min-size 2 --top-candidates 5
```

Output: `data/judge_<date>/{cluster_summary.json, pattern_report.md, candidate_skills.json}`.

### 3) Synth — sinh skill draft + proposal

```bash
uv run python scripts/synth.py \
    --candidates data/judge_<date>/candidate_skills.json \
    --top 3 --timeout 120
```

Output: `data/skills_<date>_proposal/{PROPOSAL.md, accept.py, <skill-name>/...}`.

### 4) Accept — cài skill bạn duyệt

```bash
python data/skills_<date>_proposal/accept.py
```

Hoặc non-interactive: `python ... accept.py 1 3`.

## Tests

```bash
uv run pytest
```

## Tài liệu

- PRD: `docs/products/PRD.md`
- Schema 7 lớp field: `docs/agent_responce/data_goal.md`
- Lượt 1 implementation notes: `docs/agent_responce/session_notes.md`
- Design spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-13-pattern-end-to-end-pipeline.md`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with 4-step pipeline usage"
```

---

### Task 18: Full-suite smoke + final commit

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass (aggregator: 11, claude_runner: 8, render_proposal: 2, accept_template: 1). Total ≥ 22.

- [ ] **Step 2: Run judge entrypoint smoke (no LLM)**

```bash
uv run python -c "
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
import judge  # noqa: F401 — checks all imports resolve
import synth  # noqa: F401
print('entrypoints import cleanly')
"
```

Expected: prints `entrypoints import cleanly`.

- [ ] **Step 3: Verify git status is clean**

```bash
git status
```

Expected: `nothing to commit, working tree clean` (or only untracked `data/` which is gitignored).

- [ ] **Step 4: Tag the milestone**

```bash
git log --oneline | head -20
```

Expected: see the chain of commits from Task 1 through Task 17.

---

## Post-plan: pre-demo verification (do NOT skip)

These are checks for **you (Tuan Anh)** to do on T2/T3, not the implementing agent:

1. **Skill-creator headless test** (T2 morning, decision gate for synth Path A):
   ```bash
   claude -p "Use the skill-creator skill. Create a tiny throwaway skill called 'hello_pattern_test' in /tmp/test_skill/. SKILL.md should just say hello."
   ls /tmp/test_skill/
   ```
   - If `SKILL.md` appears → Path A works, no action needed.
   - If not → Path B will be the primary path; that's already wired.

2. **Skill activation in Cowork test** (CN, demo backup plan):
   - Place a trivial test skill in `~/.claude/skills/test_trigger/SKILL.md` with a unique trigger phrase.
   - Open Claude Cowork → use the trigger phrase → check whether skill loads.
   - If yes → demo step 5 stays in Cowork.
   - If no → demo step 5 happens in Claude Code instead. Update demo script.

3. **Simulated workload brief for interns** (CN):
   - Run 5 task types × 5 reps each across 3 people. See spec §8.1.
   - Each rep is a fresh Claude Cowork session.
   - Task D explicitly should retry intentionally 1–2 times to seed `inefficient` signal.

4. **Pre-demo dry run** (T4 morning):
   - Wipe `data/judge_*/` and `data/skills_*/`.
   - Re-run `scan.py` → `judge.py` → `synth.py` end-to-end with the simulated dataset.
   - Confirm at least 1 accepted candidate, accept.py works on a fresh terminal.

---

## Self-review check (already done by writer, recorded here)

- **Spec coverage:** All 6 decisions chốt have tasks. Task 1 covers deps (decision #6 needs Jinja2/Click). Tasks 4-7 implement decision #4 (rule-based aggregator). Tasks 8-9 implement decision #2 (Claude Code headless). Tasks 10-12 implement Lượt 2 with decision #3 (focused critique). Tasks 13-16 implement decision #5 (Path A + Path B) and decision #6 (PROPOSAL + accept.py).
- **Placeholder scan:** No TBD / TODO / "implement later". Every code step has full code.
- **Type consistency:** `Session`, `Cluster`, `extract_json_block`, `run_claude`, `run_claude_json`, `render_pattern_report`, `render_skill_dir`, `_emit_accept_py` names used consistently across tasks.
- **Open issues from spec:**
  - Spec §11 issue #3 (skill in Cowork): captured in Post-plan verification step 2.
  - Spec §11 issue #1 (skill-creator headless): captured as decision gate in Post-plan step 1; Path B is already a tested fallback.
  - Spec §11 issue #2 (`Path.home()` on Windows): emitted `accept.py` uses `Path.home()` and `tests/test_accept_template.py` runs with `USERPROFILE` env set (Windows-compatible).
  - Spec §11 issue #4 (rate limit): no automated mitigation; capped to top-3 candidates already and surfaced as a known risk.
