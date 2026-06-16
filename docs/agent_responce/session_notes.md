# Session notes — Khám phá log Claude cowork & build scanner

Ghi lại nguyên văn các bước đã làm trong conversation ngày **2026-06-12**.
Bổ trợ cho `data_goal.md` (chứa bảng field) và `scripts/scan.py` (implementation).

---

## 1. Bối cảnh

Mục tiêu: lấy log session của Claude Desktop (cowork mode) → trích các trường hành vi
có giá trị → feed cho **LLM-as-judge** để rút **Skill cá nhân hoá** từ pattern hay lặp.

---

## 2. Khám phá cấu trúc log Claude Desktop

Thư mục gốc:
`C:\Users\chuba\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude`

### 2.1 Các vị trí đáng chú ý

| Vị trí                                               | Vai trò                                                 |
| ---------------------------------------------------- | ------------------------------------------------------- |
| `claude-code-sessions/<userId>/<workspaceId>/`       | Metadata session (bản nhẹ)                              |
| `local-agent-mode-sessions/<userId>/<workspaceId>/`  | **Bản đầy đủ** — metadata + audit log + outputs/uploads |
| `logs/main.log` (~301 KB)                            | Log Electron renderer                                   |
| `logs/cowork-service.log`, `logs/cowork_vm_node.log` | Lifecycle VM cowork                                     |
| `cowork-enabled-cli-ops.json`                        | Account đang bật cowork (`ownerAccountId`)              |
| `claude-code-vm/2.1.170/claude.exe` (243 MB)         | Runtime Claude Code nội tuyến                           |
| `config.json`                                        | Token OAuth + GrowthBook allowlist cache                |

Với máy này: `userId = e12f6a00-…`, `workspaceId = ca1e939e-…`.

### 2.2 Cấu trúc 1 session

```
local_<sessionId>.json            ← metadata phẳng (title, model, timestamps…)
local_<sessionId>/
├── audit.jsonl                   ← log chính, JSONL có HMAC sign từng dòng
├── .audit-key                    ← key nhị phân để verify HMAC
├── .claude/                      ← state Claude Code nhúng
│   ├── .claude.json
│   ├── .credentials.json
│   ├── projects/<encoded-cwd>/<sid>.jsonl   ← queue operations
│   └── sessions/<pid>.json                  ← process metadata
├── outputs/                      ← file Claude tạo ra
└── uploads/                      ← file user upload
```

### 2.3 Các session phát hiện được (2026-06-12)

| Process name              | Title                          | Model             | Audit lines |
| ------------------------- | ------------------------------ | ----------------- | ----------- |
| `relaxed-keen-heisenberg` | Customize Claude to your role  | `claude-fable-5`  | 112         |
| `lucid-beautiful-fermat`  | Computer use capabilities test | `claude-opus-4-8` | 286         |
| `modest-nice-edison`      | Conversation notes discussion  | `claude-opus-4-8` | 41          |
| `gifted-adoring-hamilton` | Personal information           | `claude-opus-4-8` | 10          |

### 2.4 Kiểu event trong `audit.jsonl`

```
system, message, assistant, user, tool_use, tool_result,
thinking, text, tool_reference, tools_changed,
rate_limit_event, image, base64, direct
```

Mỗi dòng có `_audit_timestamp` + `_audit_hmac` → có thể audit toàn vẹn.
**Lưu ý:** `assistant` và `message` đôi khi cùng nội dung — phải dedupe bằng `uuid`.

---

## 3. Field đã chọn để feed LLM-judge

Chi tiết bảng field 7 lớp xem `data_goal.md`. Tóm tắt:

- **L0 Anchor** — `session_id`, `workspace_id`, `tool_use_id`, `parent_tool_use_id`, `uuid`
- **L1 Temporal** — `ts`, `created_at`, `last_activity_at`, `duration_seconds`
- **L2 Intent** — `title`, `intent_seed` (initialMessage), `user_text`, `<cu_window_hints>`
- **L3 Action atom** — `tool_name`, `mcp_server`, `input_summary`, `result_ok`, `error_kind`
- **L4 Workflow** — thứ tự `turn.idx` + `turn.actions[]` giữ nguyên sequence gốc
- **L5 Context/Env** — `model`, `process_name`, `user_selected_folders`, `focused_apps`
  (window title trích từ `<cu_window_hints>`), `skills_enabled`, `plugins_enabled`,
  `available_slash_commands` (skill/plugin user đã bật — tránh đề xuất trùng), MCP status
- **L6 Feedback** — `feedback_flag ∈ {correction, confirm, retry}` (heuristic)
- **L7 Outcome** — `input_tokens`, `output_tokens`, `rate_limit_hits`,
  `outputs_produced` + `outputs_names`, `uploads_produced` + `upload_names`
  (tên file = loại artifact: xlsx/png/pdf…), `tool_usage` (top tool), `mcp_usage` (top MCP server)

Heuristic feedback:

| Flag       | Cách phát hiện                                                     |
| ---------- | ------------------------------------------------------------------ |
| correction | User text chứa "không phải", "sai rồi", "làm lại", "đừng", "redo"… |
| confirm    | User text ≤ 40 ký tự, prefix "ok", "đúng", "tiếp tục", "yes"…      |
| retry      | Cùng `(tool_name, hash(input))` gọi lại trong ≤ 60 giây            |

---

## 4. Script đã build: `scripts/scan.py`

### 4.1 Config (đầu file)

```python
SOURCE_LOG_ROOT = Path(r"…\Roaming\Claude\local-agent-mode-sessions")
TARGET_DATE: str | None = None   # "YYYY-MM-DD"; None ⇒ hôm nay
```

### 4.2 Hành vi

1. Quét đệ quy `SOURCE_LOG_ROOT` tìm cặp `(local_<id>.json, local_<id>/audit.jsonl)`.
2. Giữ session nào có window `[createdAt, lastActivityAt]` chạm `TARGET_DATE`.
3. Parse `audit.jsonl`, dedupe bằng `uuid`, gom thành turns + actions theo schema 3 lớp:
   `SessionSummary → TurnRecord → ActionRecord`.
4. Mỗi session → 1 file JSONL trong
   `data/sessions_<date>_runAt_<runTs>/<processName>__<shortId>.jsonl`.
5. Sinh thêm `_index.json` liệt kê toàn bộ run.

### 4.3 Format file output

```jsonl
{"record_type": "session_summary", ...}   ← 1 dòng đầu
{"record_type": "turn", ...}              ← n dòng kế (theo thứ tự)
{"record_type": "rate_limit", ...}        ← cuối cùng nếu có
```

### 4.4 Kết quả test run đầu tiên

`4/4 sessions matched 2026-06-12` → 4 file JSONL (5–93 dòng), tổng 157 records.

Highlight: session `lucid-beautiful-fermat` (Computer use test) — 89 turns / 55 actions,
top tool `mcp__computer-use__left_click ×14`, **retry_count = 13**, 3 rate-limit hits.
Đây là candidate Skill cao nhất hiện tại.

---

## 5. Bước tiếp theo (gợi ý)

1. **Scale**: chạy `scan.py` cho khoảng nhiều ngày, đổ chung 1 nơi để judge có sample lớn.
2. **LLM-judge prompt**: viết prompt rút Skill từ JSONL theo 3 trục — *recurrence*,
   *cohesion*, *personalization marker* (đã định nghĩa ở `data_goal.md`).
3. **Skill template**: chuẩn hoá output thành `name / trigger / inputs / steps /
   success_check / personalization`.
4. **Privacy pass**: nếu chia sẻ data ra ngoài máy, cần mask PII trong `user_text` và
   loại `.credentials.json` / `oauth:tokenCache`.
5. **MCP health**: thống kê MCP `failed`/`pending` qua sessions để biết tool nào không
   ổn định (Gmail, Google Calendar đã thấy fail).

---

## 6. File liên quan

- `docs/data_goal.md` — bảng field 7 lớp đầy đủ
- `scripts/scan.py` — implementation
- `data/sessions_<date>_runAt_<runTs>/` — output run (gitignore tuỳ chọn)
