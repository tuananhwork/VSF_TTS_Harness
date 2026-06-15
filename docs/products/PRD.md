# PRD — Tự động đúc rút Skill từ hành vi user với Claude Cowork

| Field            | Value                                                               |
| ---------------- | ------------------------------------------------------------------- |
| Tên dự án        | **Pattern** — Behavior → Skill harness for Claude Cowork            |
| Ngày soạn        | 2026-06-12                                                          |
| Phạm vi MVP      | **Một nhân viên, trên máy của chính họ** (single-user, on-device)   |
| Mã nguồn         | `C:\Users\chuba\Workspace\VSF\Pattern`                              |
| Stakeholder      | Bùi Trung Hiếu (shadow), Phạm Khánh Hòa (architect), 3 intern (PIC) |
| Deadline (sơ bộ) | Báo cáo khả thi: 2026-06-12 • Sơ bộ: T2 • Test: T3 • Final CBLD: T4 |

---

## 1. Bối cảnh & Vấn đề

Nhân viên Vinhomes dùng Claude Cowork ngày càng nhiều, nhưng:

- **Mỗi người tự dò lại quy trình** mỗi lần làm việc lặp lại → mất thời gian.
- **Kinh nghiệm dùng AI không tích luỹ**: cùng một sai lầm prompt / cùng một tool gọi sai vẫn lặp.
- Anthropic đã có `skill-creator`, `/run-skill-generator`, community skill `generating-skills-from-logs`, nhưng **chưa có vòng đóng** từ log → phát hiện pattern → đề xuất Skill cá nhân hoá → người dùng review.

> Bài toán gốc *(anh Hiếu confirm)*: **Biến hành vi làm việc của nhân viên thành tri thức có thể tái sử dụng.** Giai đoạn này: replicate có chọn lọc trên chính máy user và tối ưu cho agent của user đó. **Open gate cho Meta-agent giai đoạn sau.**

---

## 2. Mục tiêu & Non-goals

### 2.1 Goals (MVP — phục vụ 1 user)

1. **Thu được signal** đủ tốt để LLM-judge phân biệt 4 loại hành vi (xem §6).
2. **Phát hiện workflow lặp lại** trong khoảng thời gian Δt do user chọn.
3. **Đề xuất Skill draft** chuẩn Anthropic (`SKILL.md` + scripts + golden test) cho từng pattern.
4. **Báo cáo gợi ý** — không tự publish; người dùng quyết định Skill nào lưu.

### 2.2 Non-goals (giai đoạn này)

- Knowledge graph cross-user/cross-domain — **hoãn (YAGNI)**.
- Tự động đẩy Skill vào marketplace — **không** (vòng quản trị thuộc Meta-agent phase).
- Tiêm context business cụ thể (HR/kế toán/IT) vào reasoning — **không** (giữ "business là sidecar"; tránh chệch hướng).
- Tự sửa workflow của user — **không** (chỉ quan sát + đề xuất).

### 2.3 Open gates (giữ chỗ cho Meta-agent)

- Schema output Phase 2 đủ phẳng để gom từ nhiều user (có `user_id`, `workspace_id`, không nhúng PII vào pattern).
- Phase 3 sinh `SKILL.md` chuẩn để pipeline Meta-agent có thể nhận lại làm input.

---

## 3. User & Scope

- **Persona**: 1 nhân viên Vinhomes dùng Claude Cowork cho 1 hoặc nhiều domain công việc.
- **Input domain**: dữ liệu log Claude Desktop **trên chính máy user** — không cần upload.
- **Output domain**: Skill draft trên cùng máy đó, lưu dưới dạng folder `.claude/skills/<name>/` để có hiệu lực ngay phiên kế tiếp.

---

## 4. Flow tổng thể — 3 lượt

```
┌──────────────────────────────────────────────────────────────────┐
│ LƯỢT 1 — EXTRACT DATA  (đã làm)                                  │
│ scripts/scan.py                                                  │
│ Quét audit.jsonl theo ngày → JSONL chuẩn 7 lớp field             │
│ data/sessions_<date>_runAt_<runTs>/<process>__<id>.jsonl         │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ LƯỢT 2 — LLM-as-JUDGE                                            │
│ Đọc JSONL của 1 user trong Δt → phát hiện:                       │
│   · workflow lặp lại                                             │
│   · hành vi kém hiệu quả                                         │
│   · điểm cá nhân hoá (preference markers)                        │
│ Output: pattern_report.jsonl + candidate_skills.json              │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ LƯỢT 3 — SKILL SYNTHESIS                                         │
│ Dùng skill-creator + candidate_skills.json → sinh:               │
│   · SKILL.md (frontmatter + trigger song ngữ + steps)            │
│   · scripts/ (deterministic actions)                             │
│   · golden_tests.md                                              │
│ Gợi ý cho user lưu / bỏ; merged skill vào ~/.claude/skills/      │
└──────────────────────────────────────────────────────────────────┘
```

Theo mô hình anh Hiếu nêu: **Finding → Judgment → Critique → Consolidator** — Lượt 2 đóng vai
*Finding + Judgment*; Lượt 3 đóng vai *Critique + Consolidator* (chưa cần Business critique vì
MVP độc lập business). Khi lên Meta-agent, thêm *business critique + final consolidator* ngoài.

---

## 5. Lượt 1 — Extract Data (đã hoàn thành)

### 5.1 Cái đã có

- `scripts/scan.py` — đọc `local-agent-mode-sessions/<userId>/<workspaceId>/local_<sessionId>/audit.jsonl`.
- Lọc theo `TARGET_DATE` (default = hôm nay).
- Output 1 JSONL/session vào `data/sessions_<date>_runAt_<runTs>/`.

### 5.2 Field đã trích (7 lớp)

Xem `docs/data_goal.md` cho bảng đầy đủ. Tóm tắt:

| Lớp            | Field then chốt                                                            |
| -------------- | -------------------------------------------------------------------------- |
| L0 Anchor      | `session_id`, `workspace_id`, `tool_use_id`, `parent_tool_use_id`          |
| L1 Temporal    | `ts`, `created_at`, `last_activity_at`, `duration_seconds`                 |
| L2 Intent      | `title`, `intent_seed`, `user_text`                                        |
| L3 Action atom | `tool_name`, `mcp_server`, `input_summary`, `result_ok`                    |
| L4 Workflow    | `turn.idx` + `turn.actions[]` giữ thứ tự gốc                               |
| L5 Context/Env | `model`, `user_selected_folders`, `process_name`                           |
| L6 Feedback    | `feedback_flag ∈ {correction, confirm, retry}` + counters                  |
| L7 Outcome     | `input/output_tokens`, `rate_limit_hits`, `outputs_produced`, `tool_usage` |

### 5.3 Test run 2026-06-12

`4/4 session match` → 4 file JSONL. Session `lucid-beautiful-fermat` (Computer use test) có
`retry_count = 13`, top tool `left_click ×14` — candidate Skill cao nhất.

### 5.4 Việc còn lại của Lượt 1

- (Tùy chọn) Mở rộng filter từ 1 ngày → range nhiều ngày để Lượt 2 có sample đủ.
- (Tùy chọn) Mask PII trong `user_text` trước khi đẩy sang Lượt 2 nếu sample chứa info nhạy cảm.

---

## 6. Lượt 2 — LLM-as-Judge

### 6.1 Input

Toàn bộ JSONL của 1 user trong cửa sổ Δt (mặc định: 7 ngày).

### 6.2 Phân loại 4 hành vi cần bắt (theo anh Hiếu)

| Loại                       | Tín hiệu trong JSONL                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------ |
| **Chốt decisions**         | Pattern `user_text` xác nhận → assistant `tool_use` có side-effect (write/delete)    |
| **Kém hiệu quả / lỗi lặp** | `feedback_flag = retry` hoặc `correction` cao; cùng `(tool_name, hash(input))` lặp   |
| **Nhận thức hệ thống kém** | `user_text` dài bất thường / lặp prompt; `intent_seed` mơ hồ → nhiều turn correction |
| **Điều phối quy trình**    | Chuỗi `tool_use` ổn định ≥ N lần qua các session, kèm `success_check` (kết quả ok)   |

### 6.3 3 trục đánh giá khi rút pattern (từ `data_goal.md`)

1. **Recurrence** — chuỗi `(tool, input-template)` lặp ≥ k lần qua các session.
2. **Cohesion** — cùng phục vụ 1 `title` / `intent_seed`.
3. **Personalization marker** — field ổn định riêng user (folder, file naming, app id, ngôn ngữ, slash command).

### 6.4 Pipeline judge (đề xuất)

```
[scan output JSONL]
   ↓
A. Aggregator (deterministic Python)
   - Gom theo intent_seed/title bằng embedding clustering
   - Tính frequency, retry_rate, avg_duration mỗi cluster
   - Loại cluster size < threshold
   ↓
B. Judge LLM (Claude headless / Cowork session)
   Prompt = data_goal.md (schema) + cluster_summary + 3 trục
   Output: candidate_skills.json — mỗi candidate gồm:
     {
       name, trigger_intent, action_template,
       personalization, evidence (session_ids + turn_idxs),
       score: {recurrence, cohesion, personalization},
       behavior_class: decision|inefficient|low-literacy|process,
       risk_flags: [write_action, deletes_files, ...]
     }
   ↓
C. Critique LLM (lượt phản biện)
   - Loại candidate trùng skill có sẵn (~/.claude/skills/)
   - Loại candidate dưới ngưỡng tổng điểm
   - Bổ sung "anti-pattern" cho nhóm inefficient
```

### 6.5 Deliverable Lượt 2

- `data/judge_<date>_<window>/pattern_report.md` — báo cáo human-readable.
- `data/judge_<date>_<window>/candidate_skills.json` — input cho Lượt 3.

### 6.6 Nguyên tắc

- **Không tiêm context business** vào prompt judge. Business là sidecar.
- Judge **không tự sửa** workflow — chỉ phát hiện và đề xuất.
- Với nhóm `inefficient`: ưu tiên đề xuất **anti-pattern note** thay vì Skill thực thi (đỡ rủi ro).

---

## 7. Lượt 3 — Skill Synthesis

### 7.1 Input

`candidate_skills.json` từ Lượt 2.

### 7.2 Nguyên tắc xây Skill (theo anh Hiếu)

1. **Maximum deterministic actions using script** — bước nào lặp đúng input → đẩy vào `scripts/`.
2. **Heuristic/reasoning using LLM judgement** — bước cần phán đoán → để cho LLM trong SKILL.md.
3. **Hook to guard or provide additional context** — trước/sau action có side-effect, dùng hook.

### 7.3 3 câu hỏi mỗi Skill phải trả lời

| Câu hỏi               | Tài liệu kèm                                                       |
| --------------------- | ------------------------------------------------------------------ |
| Khi nào thì viết      | `trigger` (description) song ngữ Việt–Anh trong frontmatter        |
| Viết như thế nào      | `SKILL.md` steps + reference scripts                               |
| Có tính sử dụng không | `tests/unit/` cho script + `tests/eval/golden.md` cho LLM behavior |

### 7.4 Pipeline synthesis

```
candidate_skills.json
   ↓
1. Group by behavior_class
   ↓
2. Per candidate:
   a. Gọi skill-creator (Anthropic) với candidate + evidence
   b. Sinh SKILL.md, trigger song ngữ
   c. Sinh script khi action_template ổn định ≥ 90%
   d. Sinh 3–5 golden test từ evidence sessions
   ↓
3. Self-eval (skill-creator hỗ trợ)
   ↓
4. Render PROPOSAL.md cho user:
   "Phát hiện X pattern, đề xuất Y skill. Chọn skill nào lưu?"
   ↓
5. User chấp nhận → cp -r vào ~/.claude/skills/<name>/
```

### 7.5 Deliverable Lượt 3

- `data/skills_<date>_proposal/` — folder chứa các Skill draft + `PROPOSAL.md`.
- Sau khi user duyệt: skill có hiệu lực ngay phiên Claude kế tiếp.

---

## 8. Tiêu chí thành công (MVP)

| Tiêu chí                                                                | Ngưỡng đề xuất                |
| ----------------------------------------------------------------------- | ----------------------------- |
| Tỷ lệ pattern Lượt 2 phát hiện → user xác nhận "đúng quy trình của tôi" | ≥ 70%                         |
| Tỷ lệ Skill Lượt 3 đề xuất → user chấp nhận lưu                         | ≥ 30%                         |
| Tỷ lệ Skill đã lưu được trigger lại trong 7 ngày kế tiếp                | ≥ 50% (đo qua scan lượt tiếp) |
| Số false-positive pattern (đề xuất nhưng user reject)                   | ≤ 30%                         |
| Skill có thao tác ghi/xoá có bước confirm                               | 100%                          |

Vòng feedback: scan lượt sau sẽ thấy skill nào được trigger / bị user sửa output → đầu vào cho Lượt 2 chu kỳ kế tiếp (vòng tự tối ưu).

---

## 9. Rủi ro chính

| Rủi ro                                                     | Mức   | Biện pháp                                                               |
| ---------------------------------------------------------- | ----- | ----------------------------------------------------------------------- |
| Sample 1 user, 1 tuần quá ít → judge over-fit              | Cao   | Yêu cầu ≥ 3 lần lặp/cluster; pilot ≥ 2 tuần trước khi tin output        |
| Skill sinh ra dùng tool có side-effect (delete, send mail) | Cao   | `risk_flags` trong candidate; bắt buộc confirm hook; loại auto-publish  |
| PII trong `user_text` lọt vào Skill draft                  | Cao   | Bước mask trước Lượt 2; reviewer check trước khi lưu                    |
| Judge bám business → mất tổng quát                         | Trung | Prompt judge cấm context business; test trên domain trộn                |
| `audit.jsonl` thay đổi schema khi Claude update            | Trung | Pin version Claude Desktop trong README; scan.py log unknown event type |
| User không chịu review Skill proposal                      | Trung | Báo cáo gọn, top 3; nhúng vào nhịp công việc (cuối tuần)                |

---

## 10. Mốc thời gian (theo deadline anh Hiếu)

| Mốc     | Deliverable                                                                |
| ------- | -------------------------------------------------------------------------- |
| Hôm nay | Báo cáo khả thi + PRD này + scan.py chạy được trên log thật                |
| Thứ 2   | Sơ bộ Lượt 2: aggregator + prompt judge v0 + sample candidate_skills.json  |
| Thứ 3   | Test kỹ Lượt 2 + sơ bộ Lượt 3 (skill-creator integration) trên 1 candidate |
| Thứ 4   | Hoàn thiện end-to-end demo: scan → judge → 1 Skill đã lưu + gửi CBLD       |

---

## 11. Cấu trúc thư mục dự án

```
Pattern/
├── docs/
│   ├── data_goal.md             # Bảng field 7 lớp (đã có)
│   ├── session_notes.md         # Khám phá log Claude Desktop (đã có)
│   └── products/
│       ├── conversation.txt     # Bối cảnh từ chat nội bộ
│       └── PRD.md               # File này
├── scripts/
│   ├── scan.py                  # Lượt 1 (đã có)
│   ├── judge.py                 # Lượt 2 (sẽ làm — aggregator + judge runner)
│   └── synth.py                 # Lượt 3 (sẽ làm — skill-creator runner)
├── data/                        # Output runtime (gitignore-able)
│   ├── sessions_<date>_runAt_<runTs>/    # Lượt 1
│   ├── judge_<date>_<window>/            # Lượt 2
│   └── skills_<date>_proposal/           # Lượt 3
└── pyproject.toml
```

---

## 12. Mở rộng tương lai (Meta-agent — out of scope MVP)

Khi MVP đã chạy trên ≥ 5 user, mở gate sau:

- Tầng consolidation: push session summaries (đã mask) lên repo nội bộ.
- Meta-agent chạy hàng tuần trên máy chủ dedicated (Claude Code headless).
- Cross-user mining: phát hiện pattern xuất hiện ở ≥ 2 user → ứng viên Skill org-wide.
- Vòng quản trị: skill owner review PR → merge → publish plugin marketplace nội bộ.

Tham khảo kiến trúc chi tiết: phần "Tầng 1/2/3 + Vòng quản trị" trong `conversation.txt`.

---

## 13. Phụ lục — Tham chiếu

- `docs/session_notes.md` — quá trình khám phá log Claude Desktop.
- `docs/data_goal.md` — bảng 7 lớp field + schema record + heuristic feedback.
- `docs/products/conversation.txt` — chat nội bộ làm nguồn yêu cầu.
- Skill tham chiếu: `human-analyzer`, `product-spec` (anh Hiếu) — nguyên lý "deterministic + heuristic + hook".
- Skill tham chiếu Anthropic: `skill-creator`, `/run-skill-generator`, `generating-skills-from-logs`.
