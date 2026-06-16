# Pattern — Behavior → Skill harness for Claude Cowork (MVP)

Quan sát hành vi user trên Claude Cowork → đề xuất Skill draft cá nhân hoá.
Spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`.

## Yêu cầu

- Python 3.12+, `uv`
- LLM provider chọn qua biến môi trường `LLM_PROVIDER`:
  - `CCS_ONE` (mặc định) — LLM call đi qua `ccs one -p` (profile `one`). `ccs`
    (Claude Code Switch) phải có trên `PATH`. `ccs` tự delegate tới `claude` nên
    Claude Code CLI cũng phải cài sẵn trên `PATH`. `claude_runner.py` tự inject
    `CCS_CLAUDE_PATH` (lấy từ `shutil.which("claude")`) vào subprocess ccs, nên
    không cần set tay — kể cả trên Windows nơi ccs mặc định dò claude bằng
    `command -v` (lỗi trên cmd.exe).
  - `CLAUDE` — gọi thẳng `claude -p` (Claude Code headless), bỏ qua ccs. Chỉ cần
    `claude` trên `PATH`. Giá trị không phân biệt hoa thường và chấp nhận
    khoảng trắng/gạch nối (`CCS ONE`, `ccs-one`).
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

### 2) Judge — triage → multi-judge debate → candidate skills

```bash
uv run python scripts/judge.py \
    --sessions-dir data/sessions_<date>_runAt_<runTs> \
    --top-candidates 5 --min-recurrence 2 --max-deepdive 5
```

Hai lượt:
- **Triage** (LLM, trên summary + `tool_sequence` + `intent_seeds`): gom task lặp
  lại, gắn `skill_type` (`process_macro` | `improvement_lesson`).
- **Recompute metric** (code, sau triage): tính lại recurrence/repeat_rate/failure_rate
  trên đúng tập `evidence.session_ids` mà LLM đã merge — số này (không phải tool-ngram
  pre-group) là số thật cho guard + consolidator; session_id bịa bị loại và ghi cờ.
- **Recurrence guard** (code): loại candidate có recurrence (đã verify) < `min-recurrence`.
- **Pass 2 — debate** (Cách B, trên full trace của từng candidate, xem
  `docs/products/agent-debate.md`), gồm 3 bước:
  - **Extract** (LLM trung lập): trích flow **có thứ tự** + điểm tốt / chưa tốt /
    cải tiến / golden tests — không chấm điểm, không quyết định.
  - **Debate** (N judge chạy **song song**, mỗi judge chấm 1 trục giá trị): MVP có
    Năng suất + Chất lượng; mỗi judge trả `{stance, axis_score, argument}`. Một judge
    lỗi không làm hỏng candidate (ghi `error`).
  - **Consolidate** (LLM): tổng hợp các verdict → `final_score` + `rejected_reason`
    + `consolidator_note`; được phép bác dù judge đồng thuận.

Chi phí mỗi candidate: `1 (extract) + N (judges) + 1 (consolidate)` call; số candidate
đã bị cap bởi `--max-deepdive`.

Output: `data/judge_<date>/{cluster_summary.json, pattern_report.md, candidate_skills.json}`
(kèm `_raw_extract_*`, `_raw_debate_*`, `_raw_consolidate_*` để debug).

Hai loại skill sinh ra:
- **process_macro**: đóng gói flow tốt hay lặp lại để gọi lại nhanh.
- **improvement_lesson**: bài học từ session lắm rework/failure — "lần sau làm X
  trước để tránh Y".

### 3) Synth — sinh skill draft + proposal

```bash
uv run python scripts/synth.py \
    --candidates data/judge_<date>/candidate_skills.json \
    --top 3 --timeout 120
```

Mỗi accepted candidate đi qua 2 stage:
- **render_skill** (LLM, 1 call): dịch candidate (VI) → nội dung skill **English**
  (description, capabilities, red flags, golden tests). Đây là phần cần reasoning.
- **assemble_skill** (code, deterministic): dựng folder skill:
  - `SKILL.md` — **chỉ chỉ dẫn**, English; 1 năng lực → flow inline, nhiều năng lực
    → index + `references/<slug>.md` mỗi năng lực.
  - `scripts/<name>` — stub trung thực cho bước deterministic (không bịa logic).
  - `evidence/<time>_<hash>/evidence.md` — toàn bộ provenance (session_ids,
    good/weak/improvement gốc, debate, metrics). **Không** nằm trong SKILL.md.
  - `golden_tests.md`.
- **validate_skill** (code): quality gate — frontmatter đúng 3 key, name==folder,
  không leak birth-history, references khớp index. Vi phạm được cờ trong
  `## Synth quality gate` của PROPOSAL.md.

Output: `data/skills_<date>_proposal/{PROPOSAL.md, accept.py, <skill-name>/...}`.
`accept.py` copy nguyên folder skill **kèm** `evidence/`.

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
