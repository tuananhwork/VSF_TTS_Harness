# Pattern — End-to-end Pipeline Design (MVP)

| Field          | Value                                                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Project        | **Pattern** — Behavior → Skill harness for Claude Cowork                                                                                    |
| Spec date      | 2026-06-13                                                                                                                                  |
| Author         | Chu Bá Tuấn Anh (S.AI.20K) + brainstorming with Claude                                                                                      |
| Companion docs | `docs/products/PRD.md` (full PRD), `docs/agent_responce/data_goal.md` (field schema), `docs/agent_responce/session_notes.md` (Lượt 1 notes) |
| Scope          | End-to-end MVP for **single-user, on-device** scenario. Lượt 1 done; this spec covers Lượt 2 (Judge) + Lượt 3 (Synthesis) + UX.             |
| Demo deadline  | 2026-06-17 (T4) — CBLD report                                                                                                               |

---

## 1. Mục tiêu spec này

Spec này định nghĩa **how** triển khai pipeline end-to-end của Pattern MVP. PRD đã chốt **what** và **why**; spec này chốt 6 quyết định thiết kế còn để mở trong PRD, đủ chi tiết để chuyển sang implementation plan.

**Không nằm trong spec:**
- Cross-user mining (Meta-agent phase)
- Auto-publish skill marketplace
- Business critique layer
- Knowledge graph index
- Multi-day delta-T auto-scheduling

---

## 2. Sáu quyết định chốt (kết quả brainstorming)

| #   | Decision                | Chốt                                                                        | Tại sao                                                                           |
| --- | ----------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1   | **Data strategy**       | Simulated workload (3 người chạy task lặp lại có chủ ý)                     | 4 sessions real không đủ recurrence cho judge; deadline 4 ngày không kịp tự nhiên |
| 2   | **LLM execution model** | Claude Code headless (`claude -p`) cho cả Lượt 2 + Lượt 3                   | User chỉ có Claude Code/Cowork subscription, không có Anthropic API key           |
| 3   | **Behavior focus**      | 2/4 loại: Process orchestration + Inefficient/retry                         | Cover được cả "skill executable" và "anti-pattern note"; tín hiệu rõ trong JSONL  |
| 4   | **Aggregator**          | Rule-based grouping (title-similarity + tool n-gram)                        | Simulated data có title chuẩn; tránh dep `sentence-transformers` (500MB)          |
| 5   | **Skill synthesis**     | Path A: skill-creator headless. Fallback B: template-fill                   | Path A leverage Anthropic skill nếu work; Path B fallback an toàn                 |
| 6   | **Proposal UX**         | `PROPOSAL.md` (passive reading) + `accept.py` minimal (interactive install) | Demo CBLD show được cả 2 — đọc tổng quan + "moment of decision"                   |

---

## 3. Pipeline tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│  LƯỢT 1 — EXTRACT  (đã có)                                       │
│  scripts/scan.py → data/sessions_<date>_runAt_<runTs>/           │
│  Output: per-session JSONL với 7 lớp field                       │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  LƯỢT 2 — JUDGE  (mới)                                           │
│  scripts/judge.py                                                │
│   ① _lib/aggregator.py     → rule-based cluster sessions         │
│   ② _lib/claude_runner.py  → subprocess `claude -p` judge prompt │
│   ③ critique INLINE trong judge prompt (no 2-stage)              │
│  Output: data/judge_<date>/                                       │
│   ├── cluster_summary.json     (deterministic aggregator output) │
│   ├── pattern_report.md        (human-readable)                  │
│   └── candidate_skills.json    (input cho Lượt 3)                │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  LƯỢT 3 — SYNTHESIS  (mới)                                       │
│  scripts/synth.py                                                │
│   ① Path A: subprocess `claude -p "Use skill-creator..."`        │
│   ② Path B fallback: template-fill nếu A fail (timeout 120s)     │
│   ③ Render PROPOSAL.md + emit accept.py                          │
│  Output: data/skills_<date>_proposal/                            │
│   ├── PROPOSAL.md                                                 │
│   ├── accept.py                                                   │
│   └── <skill-name>/                                               │
│       ├── SKILL.md                                                │
│       ├── scripts/                                                │
│       └── golden_tests.md                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Khác PRD ở điểm nào (lý do)

- **Critique merge vào judge prompt** thay vì LLM call riêng (PRD §6.4 bước C). Tiết kiệm 1 lượt call, simulated data scale nhỏ nên không cần 2-stage. Trade-off: critique kém độc lập hơn.
- **Aggregator bỏ embedding** — rule-based (decision #4).
- **Synth chỉ chạy top-3 candidate** thay vì all — tiết kiệm token Claude Code subscription cho demo.

---

## 4. Lượt 2 — Judge (chi tiết)

### 4.1 Aggregator — `scripts/_lib/aggregator.py`

Input: tất cả `*.jsonl` trong `data/sessions_<date>_runAt_<runTs>/` qua N ngày (CLI flag `--date-range`).

Bước:

1. Load `record_type=session_summary` của mỗi file → list `Session` objects.
2. **Group theo tool n-gram (n=3):** với mỗi session, lấy `tool_usage` top-3 (theo count desc) → set key `{"scan_file", "edit_file", "run_test"}`. Hai session cùng cluster nếu **Jaccard(setA, setB) ≥ 0.6** (≥ 2 tool trùng trên 3). Đại diện cluster là set hợp.
3. **Group theo title-similarity:** trong mỗi cluster ở bước 2, sub-cluster bằng `title` normalize (lowercase, remove punctuation, Jaccard token overlap ≥ 0.5).
4. **Loại cluster size < 2** cho MVP (PRD đề xuất ≥ 3 cho production; hạ ngưỡng để demo có data).
5. **Compute cluster metrics** per cluster:
   - `recurrence`: số session trong cluster
   - `retry_rate`: avg(`retry_count` / `total_actions`)
   - `correction_rate`: avg(`correction_count` / `total_user_turns`)
   - `avg_duration_seconds`, `total_tokens`
   - `behavior_class_hint`: `"process"` nếu retry_rate < 0.1 và recurrence ≥ 3; `"inefficient"` nếu retry_rate ≥ 0.2; `"unclear"` còn lại

Output: `data/judge_<date>/cluster_summary.json` — array of clusters with metrics + evidence (session_id list, top tool sequence, sample turn_idxs).

### 4.2 Judge caller — `scripts/_lib/claude_runner.py` + `judge_prompts.py`

Prompt template (`judge_prompts.py`):

```
Bạn là judge phân tích pattern hành vi user trên Claude Cowork.
Focus 2 hành vi: PROCESS_ORCHESTRATION + INEFFICIENT_RETRY.
Tham chiếu schema 7 lớp ở docs/agent_responce/data_goal.md.

Với mỗi cluster dưới đây, hãy:
1. Xác định behavior_class ∈ {process, inefficient, not_a_pattern}
2. Đặt tên pattern (snake_case, ≤ 30 ký tự)
3. Mô tả trigger_intent song ngữ Việt-Anh (khi nào dùng skill này)
4. Trích action_template (chuỗi tool + input shape)
5. Score: recurrence (1-5), cohesion (1-5), personalization (1-5)
6. Risk flags: [write_action, deletes_files, external_api, sends_message, ...]

CRITIQUE INLINE (judge tự đóng cả vai critique):
- Trùng skill đã cài (~/.claude/skills/)? → loại
- Score tổng < 9? → loại
- Cluster size < 2? → loại (không đủ recurrence cho MVP)
- Pattern quá generic ("file_edit", "ask_question")? → loại

Output STRICT JSON array of candidate_skills, schema:
{
  "name": "...",
  "trigger_intent": {"vi": "...", "en": "..."},
  "action_template": [{"tool": "...", "input_shape": "..."}, ...],
  "evidence": {"session_ids": [...], "turn_idxs": [...]},
  "score": {"recurrence": int, "cohesion": int, "personalization": int},
  "behavior_class": "process|inefficient",
  "risk_flags": [...],
  "rejected_reason": null | "duplicate|low_score|low_recurrence|too_generic"
}

INPUT clusters:
{clusters_json}

INSTALLED skills (avoid duplicates):
{installed_skills_list}
```

Caller (`claude_runner.py`):

```python
def run_judge(clusters_path, installed_skills, timeout=180):
    prompt = JUDGE_PROMPT.format(
        clusters_json=read(clusters_path),
        installed_skills_list=json.dumps(installed_skills),
    )
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout,
    )
    raw = result.stdout
    try:
        candidates = json.loads(extract_json_block(raw))
    except (json.JSONDecodeError, ValueError):
        # retry 1 lần: gửi raw output + lỗi parser cho Claude tự fix
        fix_prompt = (
            "Fix the JSON below to match the schema. Output JSON only, "
            f"no prose.\n\nOriginal:\n{raw}\n\nError: {sys.exc_info()[1]}"
        )
        fixed = subprocess.run(
            ["claude", "-p", fix_prompt], capture_output=True, text=True, timeout=60
        )
        candidates = json.loads(extract_json_block(fixed.stdout))
    return candidates
```

Validate JSON shape, retry 1 lần nếu fail. Log raw output `data/judge_<date>/_raw_judge_output.txt` để debug.

### 4.3 Pattern report — `scripts/_lib/render_proposal.py`

`pattern_report.md` (Jinja2 template):
- Tóm tắt: X clusters → Y candidates → Z passed critique
- Per candidate: name, behavior_class, score breakdown, top 3 evidence sessions
- Mỗi evidence: `<session_id>` + tool sequence + link tới file JSONL

### 4.4 CLI signature

```bash
python scripts/judge.py \
    --date-range 2026-06-13..2026-06-16 \
    --threshold-recurrence 2 \
    --top-candidates 5
```

---

## 5. Lượt 3 — Synthesis (chi tiết)

### 5.1 Path A — skill-creator headless

Per candidate trong `candidate_skills.json` (top-3 only):

```python
prompt = f"""
Use the skill-creator skill. Create a new skill with these inputs:

NAME: {candidate.name}
TRIGGER (bilingual VI/EN): {candidate.trigger_intent}
ACTION SEQUENCE: {candidate.action_template}
EVIDENCE: {candidate.evidence}

OUTPUT FOLDER: {output_dir}/{candidate.name}/

Requirements:
- SKILL.md with frontmatter (name, description bilingual)
- scripts/ folder if action has deterministic steps
- golden_tests.md with 3 test cases from evidence
- If skill has write/delete actions → add confirm hook reference
"""
result = subprocess.run(["claude", "-p", prompt], timeout=120)
```

**Fail detection:** check `{output_dir}/{candidate.name}/SKILL.md` exists sau 120s. Nếu không → fallback B.

### 5.2 Path B — Template fallback

`_lib/synth_templates/`:
- `SKILL.md.j2` với placeholders: `{{name}}`, `{{trigger_vi}}`, `{{trigger_en}}`, `{{steps}}`, `{{frontmatter}}`
- `golden_tests.md.j2` placeholder

Subprocess `claude -p` ngắn hơn để fill placeholder:

```
Given candidate JSON: {candidate}
Fill these fields as plain text:
- trigger_vi (Vietnamese, 1-2 sentence): when user wants to ...
- trigger_en (English, 1-2 sentence): when user wants to ...
- steps_markdown: 1. ... 2. ... 3. ...
- golden_test_1, golden_test_2, golden_test_3: example query + expected output

Return STRICT JSON.
```

Parse → render template → write file. Mất phần self-eval và scripts/ folder (sẽ empty).

### 5.3 PROPOSAL.md generator

Jinja2 template, render từ candidate_skills.json + per-candidate output dir:

```markdown
# Skill Proposal — <date>

## Tóm tắt
- N candidates phát hiện từ M sessions (Δt = K ngày)
- Top X passed critique → đề xuất review

## Top Candidates

### 1. <name>  (score: <total>/15)
**Behavior class:** <class>
**Trigger (VI):** ...
**Trigger (EN):** ...
**Evidence:** N sessions
- `<session_id>` turn X-Y: <tool sequence>
- ...
**Recommended action:** `python accept.py 1`
**Risk flags:** [...]
**Synth path:** A (skill-creator) | B (template)

...

## Cách dùng accept.py
```bash
python data/skills_<date>_proposal/accept.py
```
```

### 5.4 `accept.py` — minimal interactive installer

~50 dòng, sinh ra mỗi run:

```python
# Read PROPOSAL meta (sidecar _proposal_meta.json sinh kèm)
# Iterate candidates, show summary, prompt y/n
# Nếu y → shutil.copytree("./<name>/", Path.home() / ".claude/skills" / name)
# Print "Installed. Active in next Claude session."
```

CLI: `python accept.py` (interactive) hoặc `python accept.py 1 3` (install candidate 1 và 3 trực tiếp).

### 5.5 CLI signature

```bash
python scripts/synth.py \
    --candidates data/judge_2026-06-13/candidate_skills.json \
    --top 3 \
    --timeout 120
```

---

## 6. Cấu trúc thư mục mục tiêu

```
Pattern/
├── docs/
│   ├── agent_responce/             (đã có — data_goal.md, session_notes.md)
│   ├── products/                   (đã có — PRD.md, conversation.txt)
│   └── superpowers/specs/
│       └── 2026-06-13-pattern-end-to-end-design.md   ← spec này
│
├── scripts/
│   ├── scan.py                     (đã có — Lượt 1)
│   ├── judge.py                    ← Lượt 2 entry point
│   ├── synth.py                    ← Lượt 3 entry point
│   └── _lib/
│       ├── __init__.py
│       ├── aggregator.py
│       ├── claude_runner.py        (subprocess wrapper + timeout + retry)
│       ├── judge_prompts.py
│       ├── render_proposal.py
│       └── synth_templates/
│           ├── SKILL.md.j2
│           └── golden_tests.md.j2
│
├── tests/
│   ├── conftest.py
│   ├── test_aggregator.py
│   ├── test_render_proposal.py
│   ├── test_claude_runner.py       (mock subprocess)
│   └── fixtures/
│       └── sample_sessions/        (3-4 jsonl mẫu)
│
├── data/                           (gitignored runtime)
│   ├── sessions_<date>_runAt_<runTs>/
│   ├── judge_<date>/
│   └── skills_<date>_proposal/
│
├── README.md                       (cập nhật)
├── pyproject.toml                  (+ jinja2, click, pytest)
└── (xóa main.py)
```

**Deps thêm:** `jinja2`, `click`, `pytest` (dev). Không thêm `sentence-transformers`/`torch`.

---

## 7. Test strategy

| Component                      | Test type                                          | Coverage target                      |
| ------------------------------ | -------------------------------------------------- | ------------------------------------ |
| `aggregator.py`                | Unit test (pytest) + fixture từ 4 sessions hiện có | ≥ 80%                                |
| `render_proposal.py`           | Unit test render với candidate JSON mock           | ≥ 80%                                |
| `claude_runner.py`             | Mock subprocess + verify retry/timeout logic       | ≥ 80%                                |
| `judge.py`, `synth.py` (entry) | Smoke test với fixture, không call Claude thật     | Smoke pass                           |
| LLM judge prompt               | Manual golden eval trên 5 cluster mẫu              | Đạt với recall ≥ 70%                 |
| Skill draft output             | Manual review CBLD demo T4                         | 1 skill draft chạy được trong Cowork |

Không unit test LLM call (kết quả không deterministic).

---

## 8. Roadmap

| Ngày     | Việc bạn (+intern)                                   | Việc code                                                                                                               | Milestone                                                            |
| -------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| CN 14/06 | Brief intern 5 task types; bắt đầu simulate workload | Setup `tests/`, pyproject deps, xóa `main.py`, implement `aggregator.py` + unit test, `claude_runner.py` wrapper        | Aggregator pass test với fixture                                     |
| T2 15/06 | Tiếp tục simulate; scan log thật                     | Implement `judge.py` + `judge_prompts.py` + `render_proposal.py`. Chạy thử end-to-end                                   | `candidate_skills.json` có ≥ 2 candidate (1 process + 1 inefficient) |
| T3 16/06 | Hỗ trợ test simulate edge case                       | Implement `synth.py` path A. Decision gate sáng: A work hay phải B. Implement B nếu cần. `accept.py`. Tune prompt judge | Full pipeline ra `PROPOSAL.md` + ≥ 1 skill draft hoàn chỉnh          |
| T4 17/06 | Dry-run, slide demo, gửi CBLD                        | Polish, `README.md`, demo flow                                                                                          | Demo 5 phút + báo cáo CBLD gửi đi                                    |

### 8.1 Simulated workload — 5 task types

Bạn + intern Sơn + intern Hùng, mỗi người chạy 5 task × 5 lần = 25 sessions/người (~75 tổng):

- Task A: "Tóm tắt 1 file PDF/docx" (file khác nhau mỗi lần)
- Task B: "Tạo PRD ngắn từ 1 ý tưởng"
- Task C: "Review 1 đoạn code Python"
- Task D: "Tìm và đọc file trong workspace" (**intentional retry 1-2 lần** để sinh inefficient signal)
- Task E: "Gen prompt cho 1 use case"

### 8.2 Demo flow CBLD (5 phút)

1. Show `scan.py` chạy → 75 sessions JSONL (10s)
2. Show `judge.py` chạy → mở `pattern_report.md`, scroll candidates (1min)
3. Show `synth.py` chạy → mở `PROPOSAL.md`, đọc 1 skill (1min30)
4. Show `accept.py` interactive: chọn skill → install vào `~/.claude/skills/` (1min)
5. Mở Claude Cowork → trigger skill mới → nó chạy đúng (1min30)

Pre-record demo video backup (phòng case live fail network/Claude down).

---

## 9. Rủi ro & mitigation

| #   | Rủi ro                                                                    | Likelihood      | Impact   | Mitigation                                                                       |
| --- | ------------------------------------------------------------------------- | --------------- | -------- | -------------------------------------------------------------------------------- |
| 1   | Skill-creator headless không trigger được                                 | Med             | High     | Fallback B template-fill; decision gate T3 sáng                                  |
| 2   | Simulated data quá "sạch" → judge ra candidate vô nghĩa                   | Med             | Med      | Brief intern intentional retry; threshold ≥ 2                                    |
| 3   | Claude Code rate-limit subscription                                       | Med             | Med      | Cap top-3, expo backoff, spaced theo giờ                                         |
| 4   | Prompt judge ra JSON sai format                                           | High            | Low      | Validate + retry 1 lần, log raw output                                           |
| 5   | `audit.jsonl` schema thay đổi nếu Claude update                           | Low             | High     | Pin version Claude Desktop, scan.py log unknown event                            |
| 6   | Demo T4 fail live (network, Claude down)                                  | Low             | Critical | Pre-record demo video backup; có JSON sample sẵn                                 |
| 7   | PII trong user_text lọt vào skill draft                                   | Low (simulated) | Med      | Skip mask cho MVP; ghi vào "future work" production                              |
| 8   | Skill cài `~/.claude/skills/` không active trong Cowork (chỉ Claude Code) | Med             | High     | **Test sớm CN**; nếu fail → reframe demo bước 5 trong Claude Code thay vì Cowork |

---

## 10. Conscious trade-offs (đã chấp nhận)

- **Critique merge vào judge prompt** (no 2-stage) → tiết kiệm 1 LLM call, mất tính độc lập critique
- **Embedding clustering → rule-based** → fragile với title viết khác, nhưng simulated data sẽ chuẩn
- **Top-3 candidate cho synth** → tiết kiệm token, có thể miss candidate hay
- **Threshold recurrence = 2** (thay vì 3) → có data show demo, có nguy cơ false positive
- **No PII mask cho MVP** → simulated data, không nhạy cảm. Production phải có
- **Synth fallback B mất self-eval + scripts/ folder** → skill chất lượng kém hơn path A
- **Test LLM call: không có** → smoke test entry point, golden eval manual

---

## 11. Open issues — cần xử lý sớm

| #   | Issue                                                                                    | Khi nào test                 | Plan B nếu hỏng                                   |
| --- | ---------------------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------------- |
| 1   | Skill-creator có chạy headless `claude -p` không?                                        | CN tối hoặc T2 sáng          | Fallback B đã design sẵn                          |
| 2   | `Path.home() / ".claude/skills/"` resolve sao trên Windows?                              | CN khi implement `accept.py` | Hardcode `C:\Users\<user>\.claude\skills\` + warn |
| 3   | Skill cài `~/.claude/skills/` có active trong **Cowork** không, hay chỉ **Claude Code**? | **CN — ưu tiên cao nhất**    | Reframe demo bước 5 chạy trong Claude Code        |
| 4   | Claude Code subscription rate-limit threshold?                                           | T2 khi chạy judge thật       | Spaced execution; cache prompt response           |

---

## 12. Phụ lục — Tham chiếu

- `docs/products/PRD.md` — PRD đầy đủ
- `docs/agent_responce/data_goal.md` — schema 7 lớp field
- `docs/agent_responce/session_notes.md` — Lượt 1 implementation notes
- `scripts/scan.py` — Lượt 1 code reference
- Skill tham chiếu: `human-analyzer`, `product-spec` (anh Hiếu); `skill-creator` (Anthropic)
