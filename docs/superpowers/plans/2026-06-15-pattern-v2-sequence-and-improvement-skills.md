# Pattern V2 — Sequence-aware flow + 2-tier judge + improvement skills

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans (or subagent-driven-development) to implement task-by-task. Steps use checkbox (`- [ ]`) syntax. Run `uv run pytest` green before each commit.

**Goal:** Bám sát mục tiêu dự án — *đọc hành vi user → trích flow lặp lại (có thứ tự) → LLM phân tích điểm tốt/chưa tốt → đóng gói thành SKILL để lần sau làm hiệu quả hơn.* Nâng pipeline hiện tại từ "1-pass judge trên count dict" lên kiến trúc 2 tầng, giữ được thứ tự flow và biến hành vi `inefficient` thành **improvement skill** thay vì vứt đi.

**Quyết định thiết kế đã chốt (2026-06-15):**
1. Flow **cần thứ tự** (task A: bước 1→2→3→4) → đưa `tool_sequence` + full trace lên tầng LLM.
2. Hành vi `inefficient` (lắm retry/correction) → **sinh improvement skill** (bài học cải tiến), không reject.
3. Phạm vi: **full** — kiến trúc 2 tầng (triage → deep-dive) + 2 `skill_type` (`process_macro`, `improvement_lesson`).

**Bối cảnh — vì sao đổi (xem thảo luận):**
- `scan.py` bắt được trace giàu (chuỗi action có thứ tự, text correction, retry ở bước nào) trong các record `turn`, nhưng tầng judge chỉ thấy `tool_usage` count dict → **mất thứ tự + mất nội dung correction**. Cả 2 mục tiêu (flow tuần tự + học từ lỗi) đều cần per-turn detail.
- Judge hiện gom mọi group vào **1 prompt** và **tự critique chính mình** → rủi ro scaling token + tự chấm điểm. Guard "≥2 session" sau khi bỏ `min_size` hoàn toàn phụ thuộc LLM, không có code check.

**Tech stack:** Python 3.12, pytest, Jinja2, Click, Claude Code CLI (`claude -p` qua `_lib/claude_runner.py`).

**Spec gốc:** `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md` (kiến trúc 1-pass — plan này thay phần Lượt 2).

---

## Kiến trúc đích

```
scan.py (Lượt 1)                  ── thêm tool_sequence vào session_summary
   │  audit.jsonl → per-session JSONL (summary record + turn records)
   ▼
judge.py (Lượt 2 — 2 LLM pass)
   │  ① aggregate()  : pre-group thô theo tool, tính metric (retry_rate…)
   │  ② TRIAGE (LLM #1, trên summary+tool_sequence+intent_seeds):
   │       gom session cùng task xuyên group → list candidate thô
   │       gắn skill_type ∈ {process_macro, improvement_lesson}
   │       chọn evidence.session_ids; KHÔNG viết nội dung skill
   │  ③ recurrence guard (CODE): drop candidate có <min_recurrence session
   │  ④ DEEP-DIVE (LLM #2, mỗi candidate, trên FULL TRACE của evidence):
   │       trích action_template CÓ THỨ TỰ (1→2→3→4)
   │       good_points / weak_points / improvement_notes
   │       golden_tests + risk_flags + final_score + self-critique
   ▼  candidate_skills.json (giàu) + pattern_report.md
synth.py (Lượt 3)                 ── render SKILL.md theo skill_type
   │  process_macro    → skill mô tả flow để gọi lại
   │  improvement_lesson → skill "lần sau làm X trước để tránh Y"
   ▼  skills_<date>_proposal/{PROPOSAL.md, accept.py, <skill>/...}
accept.py (unchanged)
```

**Vì sao judge ôm cả 2 pass (không tách script mới):** giữ nguyên CLI 4 bước user đã quen (scan/judge/synth/accept). Triage rẻ chạy trên summary của *tất cả* session; deep-dive chỉ chạy trên *vài* session được chọn → giải quyết luôn vấn đề token của "1 prompt ôm hết".

---

## File structure (decomposition lock-in)

```
scripts/
├── scan.py                      (modify — thêm tool_sequence vào SessionSummary)
├── judge.py                     (modify — orchestrate triage → guard → deep-dive)
├── synth.py                     (modify — render theo skill_type)
└── _lib/
    ├── aggregator.py            (modify — load + expose tool_sequence)
    ├── trace_loader.py          (new   — đọc turn records → ordered trace cho deep-dive)
    ├── judge_prompts.py         (modify — tách build_triage_prompt + build_deepdive_prompt)
    ├── candidate_schema.py      (new   — guard + normalize candidate dict, pure Python)
    ├── render_proposal.py       (modify — report + SKILL template hiện good/weak/improve)
    └── synth_templates/
        ├── SKILL.md.j2          (modify — section điểm tốt / chưa tốt / cải tiến)
        └── golden_tests.md.j2   (unchanged)
tests/
├── test_scan_sequence.py        (new — tool_sequence emit đúng thứ tự)
├── test_aggregator.py           (modify — assert tool_sequence trong to_dict)
├── test_trace_loader.py         (new — ordered trace + correction markers)
├── test_candidate_schema.py     (new — recurrence guard + skill_type normalize)
├── test_judge_prompts.py        (new — prompt chứa tool_sequence/full trace + schema v2)
└── test_render_proposal.py      (modify — render good/weak/improvement)
```

**Boundaries (giữ nguyên triết lý cũ):**
- `aggregator.py` / `trace_loader.py` / `candidate_schema.py`: pure Python, không LLM, không format output → TDD đầy đủ.
- `judge_prompts.py`: chỉ string template, không logic.
- `claude_runner.py`: **không đổi** (đã có `--model`, self-heal JSON).
- `judge.py` / `synth.py`: wiring + CLI.

---

## Candidate schema v2 (hợp đồng giữa các tầng)

**Triage output** (1 phần tử / candidate thô):
```jsonc
{
  "name": "snake_case_<=30",
  "skill_type": "process_macro" | "improvement_lesson",
  "behavior_class": "process" | "inefficient" | "not_a_pattern",
  "trigger_intent": {"vi": "...", "en": "..."},
  "evidence": {"session_ids": [...], "source_files": [...]},
  "prelim_score": {"recurrence": 1-5, "cohesion": 1-5, "personalization": 1-5},
  "rejected_reason": null | "duplicate" | "too_generic" | "not_a_pattern"
}
```

**Deep-dive output** (làm giàu candidate đã qua guard):
```jsonc
{
  // ... mọi field triage ...
  "action_template": [{"step": 1, "tool": "...", "input_shape": "..."}],  // CÓ THỨ TỰ
  "good_points": ["cách làm tốt 1", ...],            // luôn có
  "weak_points": ["điểm chưa tốt 1", ...],           // trọng tâm cho improvement_lesson
  "improvement_notes": "lần sau làm X trước để tránh Y",  // bắt buộc nếu improvement_lesson
  "golden_tests": [{"query": "...", "expected": "..."}],   // 3 cái
  "risk_flags": ["write_action" | "deletes_files" | "external_api" | "sends_message"],
  "final_score": {"recurrence": 1-5, "cohesion": 1-5, "personalization": 1-5},
  "rejected_reason": null | "low_score" | "low_recurrence" | ...
}
```

Rule kết: `process_macro` ưu tiên `action_template` rõ ràng; `improvement_lesson` bắt buộc `weak_points` + `improvement_notes` không rỗng.

---

## Phase 0 — Baseline & branch

### Task 0: Nhánh + xác nhận trạng thái sạch
- [ ] **Step 1:** `git status` — xác nhận working tree đang có thay đổi chưa commit (aggregator/judge refactor + thư mục `data/sessions_2026-06-12_...` bị xoá). **Quyết định trước khi bắt đầu:** commit hoặc stash chúng. Plan này build *trên* các thay đổi đó (aggregator đã ở dạng "loose pre-grouping").
- [ ] **Step 2:** Tạo nhánh: `git switch -c feat/v2-sequence-improvement`
- [ ] **Step 3:** `uv run pytest -q` → phải xanh (baseline 20 passed) trước khi sửa.

---

## Phase 1 — Giữ thứ tự flow (scan → aggregator)

### Task 1: `scan.py` emit `tool_sequence`
**Files:** modify `scripts/scan.py`, new `tests/test_scan_sequence.py`

- [ ] **Step 1 (TDD):** Viết `tests/test_scan_sequence.py` dựng 1 audit.jsonl nhỏ (2 assistant turn, mỗi turn vài `tool_use` theo thứ tự) trong `tmp_path`, gọi `parse_session`, assert `summary.tool_sequence == ["Read", "Grep", "Edit", "Bash"]` (đúng thứ tự xuất hiện, không sort theo count). Chạy → đỏ.
- [ ] **Step 2:** Trong `scan.py`:
  - Thêm field `tool_sequence: list[str]` vào `@dataclass SessionSummary`.
  - Trong `parse_session`, thu thập tên tool theo thứ tự gặp trong vòng lặp `tool_use` (đã có sẵn chỗ `tool_usage[name] = ...`); append vào một list `tool_sequence`.
  - **Nén run-length:** gộp tool lặp liên tiếp thành `name` (bỏ đếm) hoặc `name×k` để giữ trace gọn — chọn `name×k` để deep-dive biết độ lặp. Helper:
    ```python
    def _compress_runs(seq: list[str]) -> list[str]:
        out: list[str] = []
        for name in seq:
            base = name.split("×")[0]
            if out and out[-1].split("×")[0] == base:
                prev = out[-1].split("×")
                k = int(prev[1]) + 1 if len(prev) == 2 else 2
                out[-1] = f"{base}×{k}"
            else:
                out.append(name)
        return out
    ```
  - Gán `tool_sequence=_compress_runs(seq)` trong `SessionSummary(...)`.
- [ ] **Step 3:** Chạy test → xanh. `uv run pytest tests/test_scan_sequence.py -v`.
- [ ] **Step 4:** Commit: `feat(scan): emit ordered tool_sequence in session_summary`.

### Task 2: `aggregator.py` load + expose `tool_sequence`
**Files:** modify `scripts/_lib/aggregator.py`, `tests/test_aggregator.py`

- [ ] **Step 1 (TDD):** Trong `test_aggregator.py`, thêm `tool_sequence` vào `_mk_session` helper và viết test:
  - `load_sessions` đọc `tool_sequence` từ record.
  - `Cluster.to_dict()["tool_sequence_per_session"]` là list các list theo đúng thứ tự. Chạy → đỏ.
- [ ] **Step 2:** Sửa `aggregator.py`:
  - Thêm `tool_sequence: list[str] = field(default_factory=list)` vào `Session` (đổi `@dataclass(frozen=True)` → giữ frozen, dùng `field`).
  - `load_sessions`: `tool_sequence=list(rec.get("tool_sequence") or [])`.
  - `to_dict()`: thêm `"tool_sequence_per_session": [s.tool_sequence for s in self.sessions]` cạnh `intent_seeds`.
- [ ] **Step 3:** Chạy `uv run pytest tests/test_aggregator.py -v` → xanh.
- [ ] **Step 4:** Commit: `feat(aggregator): carry tool_sequence through to cluster dict`.

---

## Phase 2 — Trace loader (cho deep-dive)

### Task 3: `trace_loader.py` — đọc full ordered trace của 1 session
**Files:** new `scripts/_lib/trace_loader.py`, new `tests/test_trace_loader.py`

Deep-dive cần thấy *câu user → chuỗi tool → chỗ correction/retry → outcome*, không phải count. Dữ liệu đã có trong các record `turn` mà `scan.py` ghi.

- [ ] **Step 1 (TDD):** `test_trace_loader.py`: dựng 1 JSONL (1 summary + vài turn: user turn có `feedback_flag="correction"`, assistant turn có `actions`), gọi `load_trace(path, max_turns=...)`, assert kết quả là list các bước gọn:
  ```python
  [
    {"role": "user", "text": "Tóm tắt file", "feedback": None},
    {"role": "assistant", "tools": ["Read", "Edit×2"]},
    {"role": "user", "text": "sai rồi, làm lại", "feedback": "correction"},
    ...
  ]
  ```
  Assert thứ tự giữ nguyên + marker `feedback` xuất hiện đúng turn. Chạy → đỏ.
- [ ] **Step 2:** Implement `load_trace`:
  - Đọc các record `record_type == "turn"` theo thứ tự file (đã đúng thứ tự khi `scan.py` ghi).
  - User turn → `{"role":"user","text": truncate(user_text, N), "feedback": feedback_flag}`.
  - Assistant turn → `{"role":"assistant","tools": _compress_runs([a.tool_name for a in actions]), "feedback": feedback_flag}` (retry marker nằm ở `feedback_flag`).
  - Tham số `max_turns` (vd 40) + truncate text để khống chế token; nếu vượt, giữ đầu + cuối (chỗ correction thường ở cuối).
  - Hàm phụ `load_traces(source_files: list[str], sessions_dir: Path)` trả `{session_id: trace}`.
- [ ] **Step 3:** Chạy test → xanh.
- [ ] **Step 4:** Commit: `feat(trace): load_trace for deep-dive ordered turn view`.

---

## Phase 3 — Candidate schema guard (pure Python)

### Task 4: `candidate_schema.py` — recurrence guard + normalize
**Files:** new `scripts/_lib/candidate_schema.py`, new `tests/test_candidate_schema.py`

Trả lại **code-level check** thay vì tin LLM hoàn toàn (giải quyết nhược điểm "judge tự chấm mình").

- [ ] **Step 1 (TDD):** Viết tests:
  - `apply_recurrence_guard(candidates, min_recurrence=2)` set `rejected_reason="low_recurrence"` cho candidate có `len(set(evidence.session_ids)) < 2` (giữ trong list, không xoá — đồng nhất convention "rejected vẫn xuất hiện").
  - `normalize_skill_type(c)`: nếu thiếu `skill_type`, suy ra từ `behavior_class` (`inefficient`→`improvement_lesson`, `process`→`process_macro`).
  - `split_accepted(candidates)` → `(accepted, rejected)` theo `rejected_reason`.
  Chạy → đỏ.
- [ ] **Step 2:** Implement thuần hàm, không I/O. Idempotent, không mutate input (trả dict mới hoặc copy).
- [ ] **Step 3:** Chạy test → xanh.
- [ ] **Step 4:** Commit: `feat(schema): recurrence guard + skill_type normalize`.

---

## Phase 4 — Prompts 2 tầng

### Task 5: `judge_prompts.py` — `build_triage_prompt`
**Files:** modify `scripts/_lib/judge_prompts.py`, new `tests/test_judge_prompts.py`

- [ ] **Step 1 (TDD):** Test: `build_triage_prompt(groups, installed_skills)` trả string chứa: `tool_sequence_per_session`, `intent_seeds`, từ khóa `skill_type`, và schema triage (không có `action_template`/`golden_tests`). Chạy → đỏ.
- [ ] **Step 2:** Viết prompt triage (thay phần `JUDGE_INSTRUCTIONS` hiện tại). Nội dung cốt:
  - Input là groups gom thô theo tool; dùng `intent_seeds` + `tool_sequence_per_session` để nhận diện **task lặp lại** xuyên group.
  - Với mỗi pattern: đặt `name`, **gắn `skill_type`**: `process_macro` nếu là flow tốt lặp lại đáng đóng gói; `improvement_lesson` nếu nhóm có nhiều retry/correction (hint: dùng `retry_rate`/`correction_rate`/`behavior_class_hint` của group) — *đây là tín hiệu để HỌC, không phải để loại*.
  - Chọn `evidence.session_ids` + `source_files` (cần cho deep-dive load trace).
  - Critique nhẹ ở tầng này: chỉ loại `duplicate` (trùng installed_skills) và `too_generic`. **Không** chấm điểm chi tiết, **không** loại theo recurrence (để code guard làm).
  - Output STRICT JSON array theo schema triage ở trên.
- [ ] **Step 3:** `build_judge_prompt` cũ: giữ alias để không vỡ test cũ, hoặc xoá và cập nhật test — chọn xoá + cập nhật (surgical, tránh dead code). Cập nhật mọi import.
- [ ] **Step 4:** Chạy test → xanh. Commit: `feat(judge): triage prompt with skill_type + tool_sequence`.

### Task 6: `judge_prompts.py` — `build_deepdive_prompt`
**Files:** modify `scripts/_lib/judge_prompts.py`, `tests/test_judge_prompts.py`

- [ ] **Step 1 (TDD):** Test: `build_deepdive_prompt(candidate, traces)` chứa full trace (các bước user/assistant có thứ tự), tên candidate, và schema deep-dive (có `action_template` ordered, `good_points`, `weak_points`, `improvement_notes`, `golden_tests`). Chạy → đỏ.
- [ ] **Step 2:** Viết prompt deep-dive cho **1 candidate**:
  - Cho LLM xem `trigger_intent` + **full trace** của các evidence session (từ `trace_loader`).
  - Yêu cầu:
    1. Trích `action_template` **theo đúng thứ tự** flow (bước 1→2→3→4), bám `tools` trong trace — không đảo thứ tự.
    2. `good_points`: cách làm tốt rút ra.
    3. `weak_points`: điểm chưa tốt (chỗ retry/correction trong trace là bằng chứng).
    4. `improvement_notes`: *lần sau làm gì để tốt hơn* — **bắt buộc non-empty nếu `skill_type=improvement_lesson`**.
    5. `golden_tests` (3) + `risk_flags` + `final_score`.
    6. Self-critique: nếu sau khi xem trace thấy không phải pattern thật → set `rejected_reason`.
  - Output STRICT JSON object (1 candidate đã làm giàu).
- [ ] **Step 3:** Chạy test → xanh. Commit: `feat(judge): deep-dive prompt over full ordered trace`.

---

## Phase 5 — Judge orchestration (2 pass)

### Task 7: `judge.py` — wiring triage → guard → deep-dive
**Files:** modify `scripts/judge.py`

- [ ] **Step 1:** Thêm CLI options: `--min-recurrence` (default 2), `--max-deepdive` (default 5, giới hạn số candidate gọi deep-dive để chặn chi phí), giữ `--timeout`, `--top-candidates`. **Sửa `--timeout` default về 180.0** (hiện đang 5.0 — quá ngắn cho `claude -p` thật; xem `judge.py:55`).
- [ ] **Step 2:** Luồng `main`:
  ```
  sessions = load_sessions(sessions_dir)
  clusters = aggregate(sessions); ghi cluster_summary.json (như cũ)
  # ① TRIAGE
  prompt = build_triage_prompt(cluster_dicts, installed)
  triage = run_claude_json(prompt, timeout=timeout)        # list
  triage = [normalize_skill_type(c) for c in triage]
  # ② GUARD (code)
  triage = apply_recurrence_guard(triage, min_recurrence=min_recurrence)
  accepted_triage, rejected_triage = split_accepted(triage)
  accepted_triage = accepted_triage[:max_deepdive]
  # ③ DEEP-DIVE (mỗi candidate 1 call)
  enriched = []
  for c in accepted_triage:
      traces = load_traces(c["evidence"]["source_files"], sessions_dir)
      dd = run_claude_json(build_deepdive_prompt(c, traces), timeout=timeout)
      enriched.append({**c, **dd})
  # ④ kết: sort theo final_score, cắt top-candidates, ghép rejected
  ```
  - Ghi `candidate_skills.json` = enriched (accepted, đã sort) + rejected_triage (giữ convention rejected có mặt).
  - Lưu `_raw_triage.txt` + `_raw_deepdive_<name>.txt` để debug.
- [ ] **Step 3:** Cập nhật `render_pattern_report` call (xem Task 8 cho field mới).
- [ ] **Step 4 (smoke, không LLM):** Chạy tới trước bước ① bằng `python -c` trên fixtures để xác nhận aggregate + cluster_dict có `tool_sequence_per_session`. Không gọi Claude.
- [ ] **Step 5:** Commit: `feat(judge): two-pass triage→guard→deep-dive orchestration`.

---

## Phase 6 — Synth & report theo skill_type

### Task 8: `render_proposal.py` + report template
**Files:** modify `scripts/_lib/render_proposal.py`, `tests/test_render_proposal.py`

- [ ] **Step 1 (TDD):** Cập nhật test render: candidate giờ có `skill_type`, `good_points`, `weak_points`, `improvement_notes`. Assert report hiển thị các mục này + nhóm theo `skill_type`. Chạy → đỏ.
- [ ] **Step 2:** Sửa `_PATTERN_REPORT_TMPL`: mỗi candidate hiện `skill_type`, action_template (ordered), **Điểm tốt / Điểm chưa tốt / Cải tiến**. Cluster section thêm dòng `tool_sequence`.
- [ ] **Step 3:** Chạy test → xanh. Commit: `feat(report): show skill_type + good/weak/improvement`.

### Task 9: `SKILL.md.j2` + `synth.py` render theo skill_type
**Files:** modify `scripts/_lib/synth_templates/SKILL.md.j2`, `scripts/synth.py`, `tests/test_render_proposal.py`

- [ ] **Step 1 (TDD):** Test `render_skill_dir` với candidate `skill_type=improvement_lesson`: SKILL.md phải chứa section "Điểm chưa tốt" + "Cách làm tốt hơn lần sau" với `improvement_notes`. Với `process_macro`: chứa "Các bước" theo `action_template` ordered. Chạy → đỏ.
- [ ] **Step 2:** Sửa `SKILL.md.j2` thêm block điều kiện theo `skill_type` + render `action_template` (ordered, thay vì chỉ `steps_markdown` tự do). Cập nhật `render_skill_dir` context để truyền field mới.
- [ ] **Step 3:** Sửa `synth.py`:
  - `_path_a_prompt` / `_path_b_fill_prompt`: truyền `skill_type`, `good_points`, `weak_points`, `improvement_notes`, `action_template` ordered.
  - Path A prompt: yêu cầu skill-creator sinh skill **đúng loại** (macro vs lesson).
  - `accepted = [c for c in all if not c.get("rejected_reason")]` — giữ nguyên; giờ bao gồm cả improvement_lesson.
- [ ] **Step 4:** Chạy `uv run pytest` toàn bộ → xanh. Commit: `feat(synth): render process_macro vs improvement_lesson skills`.

---

## Phase 7 — E2E & docs

### Task 10: `e2e.py` + README
**Files:** modify `e2e.py`, `README.md`

- [ ] **Step 1:** `e2e.py`: thêm pass options mới (`--min-recurrence`, `--max-deepdive`) xuống `judge.py`. Giữ `--sessions-dir` để test bằng dir có sẵn.
- [ ] **Step 2:** Chạy thật 1 lần với sessions dir có sẵn: `uv run e2e.py --sessions-dir data/sessions_<...>` (cần `claude` trên PATH). Kiểm tra: `candidate_skills.json` có cả `skill_type`, `action_template` ordered, và ít nhất 1 `improvement_lesson` nếu data có session lắm retry.
- [ ] **Step 3:** README: cập nhật mô tả Lượt 2 (2-pass), thêm flag mới, nêu 2 loại skill output.
- [ ] **Step 4:** Commit: `docs: V2 two-pass judge + improvement skills in README/e2e`.

### Task 11: Hoàn tất nhánh
- [ ] **Step 1:** `uv run pytest -q` → toàn xanh.
- [ ] **Step 2:** Dùng superpowers:finishing-a-development-branch để chọn merge/PR.

---

## Rủi ro & cân nhắc

- **Chi phí LLM tăng:** deep-dive = N call (N ≤ `--max-deepdive`). Mitigation: guard recurrence chạy *trước* deep-dive nên chỉ candidate đáng giá mới tốn call; trace bị truncate theo `max_turns`.
- **Token trace lớn:** session dài → trace to. `load_trace` truncate text + giữ đầu/cuối (correction thường ở cuối). Theo dõi, có thể thêm tóm tắt trace nếu vượt.
- **improvement_lesson dễ "generic":** prompt deep-dive bắt buộc `improvement_notes` bám bằng chứng cụ thể trong trace (chỗ nào retry, user sửa gì) — không cho lời khuyên chung chung.
- **Không phá vỡ CLI:** vẫn 4 bước scan/judge/synth/accept; thay đổi nằm trong judge.
- **Test LLM:** mọi module thuần (scan sequence, trace_loader, candidate_schema, prompts, render) TDD đầy đủ; phần gọi `claude -p` chỉ smoke-test thủ công ở Task 10.
```
