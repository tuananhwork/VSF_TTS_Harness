# Candidate Metric Recompute (Hướng B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tính lại recurrence/repeat_rate/pivot_rate/behavior_class trên đúng tập session mà LLM đã merge (evidence.session_ids), thay vì để metric dính cứng vào tool-ngram pre-group — và đưa số thật đó cho stage có thẩm quyền (recurrence guard + deep-dive consolidator).

**Architecture:** Pipeline giữ nguyên 2 tầng: `cluster_by_tool_ngram` (code, rẻ) pre-group để gọn prompt triage → LLM triage merge ngữ nghĩa, trả candidate kèm `evidence.session_ids`. Thêm MỘT bước code thuần sau triage: `recompute_candidate_metrics` resolve session_ids → `Session`, tính lại metric trên tập đã merge, đính vào `candidate["metrics"]`, drop & ghi lại id bịa. Recurrence guard và các prompt deep-dive đọc `candidate.metrics` làm số thật.

**Tech Stack:** Python 3.12, `uv`, pytest, jinja2. Không thêm dependency. Không thêm LLM call (chỉ enrich prompt sẵn có).

---

## Bối cảnh (đọc trước)

- `scripts/_lib/aggregator.py` — `Session` dataclass (`.session_id`, `.repeat_count`, `.pivot_count`, `.total_actions`, `.total_user_turns`), `cluster_by_tool_ngram`, `_build_cluster`, `_classify`, `Cluster.to_dict`.
- `scripts/_lib/candidate_schema.py` — `apply_recurrence_guard` (hiện đếm `len(set(evidence.session_ids))`).
- `scripts/judge.py` — `main()`: `sessions = load_sessions(...)` (dòng 86) → `clusters = aggregate(sessions)` → `triage = run_claude_json(build_triage_prompt(cluster_dicts, ...))` → `triage = [normalize...]` (dòng 110) → `apply_recurrence_guard` (dòng 113) → deep-dive.
- `scripts/_lib/judge_prompts.py` — `CONSOLIDATOR_INSTRUCTIONS`, `JUDGE_TASK`. Cả `candidate` dict được serialize vào extract/judge/consolidator prompt, nên field mới `candidate["metrics"]` tự chảy vào.
- `scripts/_lib/render_proposal.py` — `_PATTERN_REPORT_TMPL`, block candidate quanh dòng 67.

**Bất biến:** metric phải là **một nguồn sự thật duy nhất** (DRY) — cùng công thức cho cluster lẫn candidate. Hàm thuần, không mutate input (theo convention `candidate_schema.py`).

## File Structure

- Modify `scripts/_lib/aggregator.py` — thêm `classify_behavior` (public, thay `_classify`), `cluster_metrics(group)`, `recompute_candidate_metrics(candidates, sessions)`; refactor `_build_cluster` xài chung; cập nhật docstring module.
- Modify `scripts/_lib/candidate_schema.py` — `apply_recurrence_guard` ưu tiên `candidate.metrics.recurrence`.
- Modify `scripts/judge.py` — chèn 1 dòng recompute giữa normalize và guard; thêm import.
- Modify `scripts/_lib/judge_prompts.py` — đánh dấu `candidate.metrics` là số thật trong CONSOLIDATOR + JUDGE_TASK.
- Modify `scripts/_lib/render_proposal.py` — hiển thị metric recompute ở block candidate.
- Tests: `tests/test_aggregator.py`, `tests/test_candidate_schema.py`, `tests/test_judge_prompts.py`, `tests/test_render_proposal.py`.

---

### Task 1: `cluster_metrics` + `classify_behavior` (nguồn sự thật metric)

**Files:**
- Modify: `scripts/_lib/aggregator.py` (vùng `_classify` dòng ~171-176, `_build_cluster` dòng ~179-205)
- Test: `tests/test_aggregator.py`

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_aggregator.py`:

```python
def test_cluster_metrics_computes_rates_and_behavior() -> None:
    from _lib.aggregator import cluster_metrics
    a = Session(
        session_id="a", process_name="a", title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=3, pivot_count=1,
    )
    b = Session(
        session_id="b", process_name="b", title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=3, pivot_count=1,
    )
    m = cluster_metrics([a, b])
    assert m["recurrence"] == 2
    assert m["repeat_rate"] == 0.3        # mean(3/10, 3/10)
    assert m["pivot_rate"] == 0.25        # mean(1/4, 1/4)
    assert m["behavior_class"] == "inefficient"   # repeat_rate >= 0.2
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_aggregator.py::test_cluster_metrics_computes_rates_and_behavior -v`
Expected: FAIL — `ImportError: cannot import name 'cluster_metrics'`.

- [ ] **Step 3: Cài đặt — thêm `classify_behavior` + `cluster_metrics`, refactor `_build_cluster`**

Thay nguyên khối `_classify` + `_build_cluster` hiện tại bằng:

```python
def classify_behavior(repeat_rate: float, recurrence: int) -> str:
    if repeat_rate >= 0.2:
        return "inefficient"
    if repeat_rate < 0.1 and recurrence >= 3:
        return "process"
    return "unclear"


def cluster_metrics(group: list[Session]) -> dict:
    """Recurrence + structural rates + behavior class cho MỘT tập session bất kỳ.
    Nguồn sự thật duy nhất cho các số này — dùng cho cả tool-ngram cluster lẫn
    recompute trên merge của LLM. Không mutate input."""
    n = len(group)
    repeat_rate = (
        sum(s.repeat_count / s.total_actions for s in group if s.total_actions)
        / max(1, sum(1 for s in group if s.total_actions))
    )
    pivot_rate = (
        sum(s.pivot_count / s.total_user_turns for s in group if s.total_user_turns)
        / max(1, sum(1 for s in group if s.total_user_turns))
    )
    return {
        "recurrence": n,
        "repeat_rate": repeat_rate,
        "pivot_rate": pivot_rate,
        "behavior_class": classify_behavior(repeat_rate, n),
    }


def _build_cluster(group: list[Session]) -> Cluster:
    n = len(group)
    m = cluster_metrics(group)
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
        repeat_rate=m["repeat_rate"],
        pivot_rate=m["pivot_rate"],
        avg_duration_seconds=avg_duration,
        total_tokens=total_tokens,
        behavior_class_hint=m["behavior_class"],
    )
```

- [ ] **Step 4: Chạy test, xác nhận pass (kèm regression)**

Run: `uv run pytest tests/test_aggregator.py -v`
Expected: PASS toàn bộ — đặc biệt `test_aggregate_metrics_classify_inefficient` vẫn xanh (refactor giữ nguyên hành vi).

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "refactor(aggregator): extract cluster_metrics + classify_behavior as single source"
```

---

### Task 2: `recompute_candidate_metrics` (tính metric trên merge của LLM)

**Files:**
- Modify: `scripts/_lib/aggregator.py` (thêm hàm sau `_build_cluster`; cập nhật docstring module dòng 1-8)
- Test: `tests/test_aggregator.py`

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_aggregator.py`:

```python
def _sess(sid: str, repeat: int, pivot: int) -> Session:
    return Session(
        session_id=sid, process_name=sid, title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=repeat, pivot_count=pivot,
    )


def test_recompute_uses_merged_evidence_not_tool_group() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    sessions = [_sess("s1", 0, 0), _sess("s2", 0, 0), _sess("s3", 0, 0)]
    # LLM merged 3 sessions into one candidate, though tool-ngram split them.
    cands = [{"name": "summarize",
              "evidence": {"session_ids": ["s1", "s2", "s3"]}}]
    out = recompute_candidate_metrics(cands, sessions)
    assert out[0]["metrics"]["recurrence"] == 3
    assert out[0]["metrics"]["behavior_class"] == "process"  # rec>=3, repeat<0.1
    assert out[0]["metrics"]["unknown_session_ids"] == []


def test_recompute_drops_hallucinated_session_ids() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    sessions = [_sess("s1", 0, 0)]
    cands = [{"name": "x", "evidence": {"session_ids": ["s1", "ghost"]}}]
    out = recompute_candidate_metrics(cands, sessions)
    assert out[0]["metrics"]["recurrence"] == 1            # only s1 is real
    assert out[0]["metrics"]["unknown_session_ids"] == ["ghost"]


def test_recompute_does_not_mutate_input() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    cands = [{"name": "x", "evidence": {"session_ids": ["s1"]}}]
    recompute_candidate_metrics(cands, [_sess("s1", 0, 0)])
    assert "metrics" not in cands[0]
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_aggregator.py -k recompute -v`
Expected: FAIL — `ImportError: cannot import name 'recompute_candidate_metrics'`.

- [ ] **Step 3: Cài đặt — thêm hàm `recompute_candidate_metrics`**

Thêm ngay sau `_build_cluster` trong `scripts/_lib/aggregator.py`:

```python
def recompute_candidate_metrics(
    candidates: list[dict], sessions: list[Session]
) -> list[dict]:
    """Tính lại metric của mỗi candidate từ ĐÚNG các session mà evidence trỏ tới
    (merge có thẩm quyền của LLM), không phải tool-ngram pre-group. session_id
    bịa (không có trong `sessions`) bị loại và ghi vào `metrics.unknown_session_ids`.
    Trả về bản copy; không mutate input."""
    by_id = {s.session_id: s for s in sessions}
    out: list[dict] = []
    for c in candidates:
        c = dict(c)
        ids = list(dict.fromkeys(c.get("evidence", {}).get("session_ids", [])))
        resolved = [by_id[i] for i in ids if i in by_id]
        unknown = [i for i in ids if i not in by_id]
        if resolved:
            m = cluster_metrics(resolved)
        else:
            m = {"recurrence": 0, "repeat_rate": 0.0, "pivot_rate": 0.0,
                 "behavior_class": "unclear"}
        m["unknown_session_ids"] = unknown
        c["metrics"] = m
        out.append(c)
    return out
```

Đồng thời cập nhật docstring module (dòng 1-8) để phản ánh bước recompute — đổi câu cuối thành:

```python
"""Rule-based session pre-grouping + post-merge metric recompute for Pattern's
Lượt 2 judge stage.

Pure Python. No LLM. `cluster_by_tool_ngram` does a loose tool-usage grouping so
the triage prompt sees manageable chunks; the LLM then merges across groups by
intent. `recompute_candidate_metrics` re-derives recurrence/rates on the LLM's
merged evidence so downstream metrics reflect the authoritative grouping, not the
tool pre-group.
"""
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `uv run pytest tests/test_aggregator.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): recompute candidate metrics on LLM-merged evidence"
```

---

### Task 3: Recurrence guard dùng recurrence đã verify

**Files:**
- Modify: `scripts/_lib/candidate_schema.py` (`apply_recurrence_guard`, dòng ~44-58)
- Test: `tests/test_candidate_schema.py`

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_candidate_schema.py`:

```python
def test_recurrence_guard_prefers_verified_metrics_recurrence() -> None:
    # Candidate cites 3 ids but only 1 was real → metrics.recurrence == 1 → reject.
    cands = [{
        "name": "a",
        "evidence": {"session_ids": ["s1", "s2", "s3"]},
        "metrics": {"recurrence": 1},
    }]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0]["rejected_reason"] == "low_recurrence"


def test_recurrence_guard_accepts_when_verified_recurrence_meets_min() -> None:
    cands = [{
        "name": "a",
        "evidence": {"session_ids": ["s1", "s2"]},
        "metrics": {"recurrence": 2},
    }]
    out = apply_recurrence_guard(cands, min_recurrence=2)
    assert out[0].get("rejected_reason") is None
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_candidate_schema.py -k verified -v`
Expected: FAIL — guard hiện đếm `session_ids` (=3) nên không reject `test_..._prefers_verified...`.

- [ ] **Step 3: Cài đặt — ưu tiên `metrics.recurrence`**

Thay thân `apply_recurrence_guard` trong `scripts/_lib/candidate_schema.py`:

```python
def apply_recurrence_guard(
    candidates: list[dict[str, Any]], *, min_recurrence: int = 2
) -> list[dict[str, Any]]:
    """Reject candidates whose recurrence is below `min_recurrence`. Prefers the
    code-verified `metrics.recurrence` (computed on the sessions that actually
    exist) when present; falls back to the distinct cited session_ids otherwise.
    Existing rejections are preserved."""
    out: list[dict[str, Any]] = []
    for c in candidates:
        c = dict(c)
        if not c.get("rejected_reason"):
            metrics = c.get("metrics")
            if metrics is not None:
                distinct = int(metrics.get("recurrence", 0))
            else:
                distinct = len(set(c.get("evidence", {}).get("session_ids", [])))
            if distinct < min_recurrence:
                c["rejected_reason"] = "low_recurrence"
        out.append(c)
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass (kèm regression)**

Run: `uv run pytest tests/test_candidate_schema.py -v`
Expected: PASS toàn bộ — các test cũ (không có `metrics`) vẫn xanh qua nhánh fallback.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/candidate_schema.py tests/test_candidate_schema.py
git commit -m "feat(guard): recurrence guard prefers code-verified metrics.recurrence"
```

---

### Task 4: Nối vào `judge.py`

**Files:**
- Modify: `scripts/judge.py` (import dòng ~25; chèn recompute giữa dòng 110 và 113)

- [ ] **Step 1: Thêm import**

Tại `scripts/judge.py`, đổi dòng import aggregator:

```python
from _lib.aggregator import aggregate, load_sessions
```

thành:

```python
from _lib.aggregator import aggregate, load_sessions, recompute_candidate_metrics
```

- [ ] **Step 2: Chèn bước recompute trước guard**

Tìm khối:

```python
        triage = [normalize_skill_name(normalize_skill_type(c)) for c in triage]

        # ── GUARD: code-level recurrence check ───────────────────────────────
        triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
```

Đổi thành:

```python
        triage = [normalize_skill_name(normalize_skill_type(c)) for c in triage]

        # ── RECOMPUTE: metric thật trên evidence đã merge (không phải tool-group)
        triage = recompute_candidate_metrics(triage, sessions)

        # ── GUARD: code-level recurrence check (dùng metrics.recurrence đã verify)
        triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
```

- [ ] **Step 3: Chạy full suite, xác nhận không regression**

Run: `uv run pytest -q`
Expected: PASS toàn bộ (logic đã được phủ ở Task 1-3; bước này chỉ là nối dây).

- [ ] **Step 4: Smoke import**

Run: `uv run python -c "import sys; sys.path.insert(0,'scripts'); import judge; print('judge imports OK')"`
Expected: in `judge imports OK`.

- [ ] **Step 5: Commit**

```bash
git add scripts/judge.py
git commit -m "feat(judge): recompute candidate metrics before recurrence guard"
```

---

### Task 5: Prompt deep-dive coi `candidate.metrics` là số thật

**Files:**
- Modify: `scripts/_lib/judge_prompts.py` (`JUDGE_TASK` dòng ~116-123; `CONSOLIDATOR_INSTRUCTIONS` dòng ~134-147)
- Test: `tests/test_judge_prompts.py`

- [ ] **Step 1: Viết test fail**

Thêm vào `tests/test_judge_prompts.py` (cạnh các test consolidator/extract hiện có; import `build_consolidator_prompt` nếu chưa có ở đầu file):

```python
def test_consolidator_prompt_marks_metrics_authoritative() -> None:
    from _lib.judge_prompts import build_consolidator_prompt
    cand = {"name": "x", "metrics": {"recurrence": 3, "repeat_rate": 0.0,
                                     "pivot_rate": 0.0, "behavior_class": "process"}}
    prompt = build_consolidator_prompt(cand, {}, [])
    assert "candidate.metrics" in prompt      # hướng dẫn dùng số thật
    assert "\"recurrence\": 3" in prompt        # số thật được serialize vào prompt
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_judge_prompts.py::test_consolidator_prompt_marks_metrics_authoritative -v`
Expected: FAIL — `"candidate.metrics" not in prompt`.

- [ ] **Step 3: Cài đặt — thêm dòng số-thật vào instruction**

Trong `CONSOLIDATOR_INSTRUCTIONS`, chèn ngay trước dòng `1. \`final_score\`:`:

```
LƯU Ý SỐ THẬT: `candidate.metrics` (recurrence / repeat_rate / pivot_rate) được
TÍNH LẠI bằng code trên đúng tập evidence đã merge — ĐÂY là số thật để chấm axis
recurrence; bỏ qua mọi behavior_class_hint per-group cũ nếu mâu thuẫn.

```

Trong `JUDGE_TASK`, chèn ngay trước dòng `Output STRICT JSON object:`:

```
Khi cần số liệu, dùng `candidate.metrics` (recurrence/repeat_rate/pivot_rate —
tính trên evidence đã merge) làm số thật.

```

- [ ] **Step 4: Chạy test, xác nhận pass (kèm regression)**

Run: `uv run pytest tests/test_judge_prompts.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/judge_prompts.py tests/test_judge_prompts.py
git commit -m "feat(prompts): mark candidate.metrics as authoritative in deep-dive"
```

---

### Task 6: Hiển thị metric recompute trong `pattern_report.md`

**Files:**
- Modify: `scripts/_lib/render_proposal.py` (`_PATTERN_REPORT_TMPL`, block candidate quanh dòng 67-69)
- Test: `tests/test_render_proposal.py`

- [ ] **Step 1: Viết test fail**

Trong `tests/test_render_proposal.py`, ở test `test_pattern_report_lists_candidates_and_clusters`, thêm key `metrics` vào dict candidate (cái candidate `summarize_pdf` đang có sẵn các field bắt buộc như `trigger_intent`, `action_template`):

```python
            "metrics": {"recurrence": 3, "repeat_rate": 0.0, "pivot_rate": 0.0,
                        "behavior_class": "process"},
```

và thêm assertion sau khi report được render:

```python
    assert "recurrence (recomputed): 3" in report
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `uv run pytest tests/test_render_proposal.py::test_pattern_report_lists_candidates_and_clusters -v`
Expected: FAIL — `"recurrence (recomputed): 3" not in report`.

- [ ] **Step 3: Cài đặt — thêm dòng metric vào template**

Trong `_PATTERN_REPORT_TMPL`, ngay sau dòng `- Trigger (EN): {{ c.trigger_intent.en }}` (dòng ~69), chèn:

```
{% if c.metrics %}
- recurrence (recomputed): {{ c.metrics.recurrence }}, repeat_rate: {{ "%.3f"|format(c.metrics.repeat_rate) }}, pivot_rate: {{ "%.3f"|format(c.metrics.pivot_rate) }}{% if c.metrics.unknown_session_ids %} — ⚠️ bỏ {{ c.metrics.unknown_session_ids | length }} session_id bịa{% endif %}
{% endif %}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `uv run pytest tests/test_render_proposal.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/render_proposal.py tests/test_render_proposal.py
git commit -m "feat(report): show recomputed candidate metrics + hallucinated-id flag"
```

---

### Task 7: Verify toàn bộ + cập nhật docs

**Files:**
- Modify: `README.md` (mục Judge), `docs/pipeline-visualization.html` (bước Judge)

- [ ] **Step 1: Full suite xanh**

Run: `uv run pytest -q`
Expected: PASS toàn bộ, output sạch.

- [ ] **Step 2: Cập nhật README mục Judge**

Trong `README.md`, ngay dưới gạch đầu dòng **Recurrence guard**, thêm:

```markdown
- **Recompute metric** (code, sau triage): tính lại recurrence/repeat_rate/pivot_rate
  trên đúng tập `evidence.session_ids` mà LLM đã merge — số này (không phải tool-ngram
  pre-group) là số thật cho guard + consolidator; session_id bịa bị loại và ghi cờ.
```

- [ ] **Step 3: Cập nhật pipeline-visualization.html (bước Judge)**

Trong `docs/pipeline-visualization.html`, ở mục mô tả Judge, thêm 1 `<li>`:

```html
<li><b>Recompute metric</b>: sau khi LLM merge, tính lại recurrence/repeat_rate/pivot_rate trên evidence thật; loại session_id bịa.</li>
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/pipeline-visualization.html
git commit -m "docs: document post-merge metric recompute in judge stage"
```

---

## Self-Review

**Spec coverage:**
- "Tính lại metric trên merge của LLM" → Task 2 (`recompute_candidate_metrics`), Task 4 (nối judge).
- "DRY: một nguồn sự thật metric" → Task 1 (`cluster_metrics` dùng chung cho cluster + candidate).
- "Số thật tới stage có thẩm quyền" → Task 3 (guard), Task 5 (consolidator/judges).
- "Verify tính thật session_ids (bonus, cùng code path)" → Task 2 (`unknown_session_ids`), Task 3 (guard dùng verified), Task 6 (cờ trong report).
- "Quan sát được" → Task 6 (report), Task 7 (docs).

**Placeholder scan:** Không có TODO/TBD; mọi step có code/command + expected output cụ thể.

**Type consistency:** `cluster_metrics` trả dict có keys `recurrence/repeat_rate/pivot_rate/behavior_class`; `recompute_candidate_metrics` thêm `unknown_session_ids`; `apply_recurrence_guard` đọc `metrics["recurrence"]`; template đọc `c.metrics.recurrence/repeat_rate/pivot_rate/unknown_session_ids` — khớp nhau. `classify_behavior(repeat_rate, recurrence)` dùng nhất quán ở `cluster_metrics`. `_build_cluster` vẫn set `behavior_class_hint` từ `m["behavior_class"]` (giữ tên field Cluster cũ — không phá `to_dict`/test hiện có).

**Lưu ý đánh đổi (không phải lỗi):** Triage chọn `skill_type` TRƯỚC khi recompute (vẫn dựa hint per-group). Đây là cố ý: triage là pass rẻ, còn consolidator — stage có thẩm quyền, được phép override — mới thấy `candidate.metrics` thật. Nếu sau calibration thấy skill_type vẫn lệch nhiều, mới cân nhắc two-pass triage (ngoài phạm vi plan này).
