## 🎯 Mục tiêu dữ liệu

Trích hành vi → LLM-judge phân cụm pattern → chuẩn hoá thành **Skill cá nhân hoá**. Cần data có đủ 3 lớp: *intent* (muốn gì), *trajectory* (làm thế nào), *outcome* (thành công/sửa lại).

---

## 📑 Bảng field gợi ý theo lớp

### Lớp 0 — Anchor (gom event theo phiên / người dùng)

| Field                        | Nguồn                         | Vai trò                   |
| ---------------------------- | ----------------------------- | ------------------------- |
| `ownerAccountId`             | `cowork-enabled-cli-ops.json` | Khoá user                 |
| `sessionId` / `cliSessionId` | `local_*.json`, `system/init` | Khoá session              |
| `parent_tool_use_id`         | mọi event audit               | Dựng cây sub-agent / Task |
| `uuid`                       | mọi event                     | Khoá event để dedupe      |
| `workspaceId`                | đường dẫn folder              | Tách project              |

### Lớp 1 — Thời gian (phát hiện nhịp làm việc)

| Field                                             | Dùng để…                                                   |
| ------------------------------------------------- | ---------------------------------------------------------- |
| `createdAt`, `lastActivityAt`, `_audit_timestamp` | Thời lượng phiên, khoảng nghỉ giữa turn                    |
| `rate_limit_event.resetsAt`                       | Pattern user "đua" với quota                               |
| Delta giữa `tool_use` → `tool_result`             | Latency, tool nào hay chậm                                 |
| Giờ trong ngày (parse từ timestamp)               | Skill theo khung giờ (morning routine, end-of-day report…) |

### Lớp 2 — Intent (user thực sự muốn gì)

| Field                                  | Vì sao quan trọng                                                 |
| -------------------------------------- | ----------------------------------------------------------------- |
| `initialMessage`                       | Câu mở phiên — intent gốc, sạch nhất                              |
| `title` (auto-gen)                     | Topic tóm tắt sẵn — dùng làm label phân cụm                       |
| Mọi `user.message.content` (role=user) | Toàn bộ chuỗi yêu cầu, kể cả correction                           |
| `<cu_window_hints>` trong prompt       | App/cửa sổ user đang nhìn (Notepad/Teams/Chrome…) → suy ra domain |
| `isReplay` flag                        | Loại bỏ event lặp khi build sequence                              |

### Lớp 3 — Action atom (đơn vị nguyên tử của Skill)

| Field                             | Ghi chú                                                                                            |
| --------------------------------- | -------------------------------------------------------------------------------------------------- |
| `tool_use.name`                   | Tool/MCP gọi (đã thấy `mcp__computer-use__left_click` x14, `screenshot` x11…)                      |
| `tool_use.input`                  | **Tham số** — quan trọng để khám phá template (URL hay nhập, query hay search, file path hay đọc…) |
| `tool_result.content`             | Kết quả — biết action nào fail/lặp lại (repeat)                                                    |
| `tools_changed`, `tool_reference` | User bật/tắt MCP, search tool nào                                                                  |
| Slash command trong prompt        | Skill đã “đóng gói” mà user dùng (vd `/review`, `/standup`)                                        |

### Lớp 4 — Workflow (chuỗi action liên tiếp)

| Field                                 | Vai trò                                               |
| ------------------------------------- | ----------------------------------------------------- |
| Thứ tự dòng trong `audit.jsonl`       | Trật tự nguyên thuỷ — dùng làm n-gram tool            |
| `assistant.thinking` block            | LLM lập kế hoạch — dấu hiệu **multi-step pattern**    |
| `direct` type event                   | Bước thực thi trực tiếp không qua tool                |
| Cặp `(tool_use → tool_result → user)` | Vòng feedback — đo độ "trơn" của workflow             |
| `parent_tool_use_id` chain            | Dựng tree sub-agent → tách macro-skill vs micro-skill |

### Lớp 5 — Context / Environment

| Field                                        | Mục đích                                      |
| -------------------------------------------- | --------------------------------------------- |
| `userSelectedFolders`, `cwd`                 | Project/codebase user hay làm                 |
| `mcp_servers[].status`                       | MCP nào *connected* → reflect tech stack quen |
| `plugins[]`, `skills[]`                      | Skill đã có — tránh đề xuất trùng             |
| `model`, `permissionMode`, `fast_mode_state` | User chọn nhanh hay sâu — preference          |
| `uploads/` filenames + `outputs/` filenames  | Loại artifact đặc thù (xlsx, pptx, png…)      |
| `cu_window_hints` app id                     | Phân lớp Office vs Browser vs IDE workflow    |

### Lớp 6 — Feedback signals (vàng cho LLM-judge)

| Tín hiệu           | Cách phát hiện                                                                          |
| ------------------ | --------------------------------------------------------------------------------------- |
| **Correction**     | 2 `user.message` liên tiếp không có tool ở giữa, hoặc keyword "không phải/sai/đừng/lại" |
| **Confirm/Accept** | User trả ngắn ("ok", "đúng", "tiếp tục") sau plan của assistant                         |
| **Retry**          | Cùng `tool_use.name` + input gần giống trong < N giây                                   |
| **Abandon**        | Session kết thúc giữa chuỗi tool đang chạy                                              |
| **Skill override** | User gõ slash command thay vì để Claude tự chọn                                         |

### Lớp 7 — Outcome / Cost

| Field                                    | Dùng để…                                            |
| ---------------------------------------- | --------------------------------------------------- |
| `input_tokens`, `output_tokens` mỗi turn | Đo độ "đắt" của pattern — Skill nên rẻ hơn baseline |
| `rate_limit_event.status`                | Pattern nào hay đẩy user chạm trần                  |
| Số `tool_result` lỗi / tổng `tool_use`   | Tỉ lệ thành công workflow                           |
| Có file trong `outputs/` cuối phiên?     | Tín hiệu *deliverable produced*                     |
| Session `isArchived=true` trước hoàn tất | Phiên bỏ dở (judge có thể loại)                     |

---

## 🧪 Schema gợi ý cho LLM-as-judge

Gộp các field trên thành 3 cấp record để judge dễ tiêu hoá:

```text
SessionRecord
 ├─ id, user, workspace, model, duration, token_total, outcome
 ├─ intent_seed: initialMessage
 ├─ topic_label: title
 └─ turns: [TurnRecord]

TurnRecord
 ├─ idx, ts, role, latency_ms
 ├─ user_text  (nếu user)
 ├─ thinking_summary (rút gọn từ thinking)
 ├─ actions: [ActionRecord]
 └─ feedback_flag: {pivot|repeat|none}   (cấu trúc, không keyword)

ActionRecord
 ├─ tool_name, mcp_server
 ├─ input_summary  (template hoá tham số)
 ├─ result_ok, error_kind
 └─ context: {cwd, focused_app, target_file}
```

---

## 🧠 Prompt-pattern cho LLM-judge tách Skill

Cho judge **3 trục đánh giá** trên mỗi cụm session/turn:

1. **Recurrence** — chuỗi (tool, input-template) lặp ≥ k lần qua sessions ⇒ candidate Skill.
2. **Cohesion** — các action trong chuỗi cùng phục vụ 1 `title`/`intent_seed`.
3. **Personalization marker** — có field nào ổn định riêng của user? (folder, file naming, app id, ngôn ngữ tiếng Việt, slash command hay dùng…)

Output Skill chuẩn hoá nên gồm: `name`, `trigger` (intent regex / slash command), `inputs`, `steps` (tool sequence dưới dạng pseudo-code), `success_check`, `personalization` (preset từ data user).

---

## ⚠️ Field nên *loại* trước khi đưa cho judge

- `.credentials.json`, `oauth:tokenCache`, `_audit_hmac`, `.audit-key` — bí mật, không có giá trị hành vi.
- `image`/`base64` payload thô — chỉ giữ metadata (kích thước, mime, alt-text).
- Tool catalog dài (init event liệt kê 100+ tool) — chỉ giữ tool *thực sự được gọi*.
- PII trong `user.message.content` — mask trước khi log dài hạn.

---

**Tóm gọn:** ưu tiên 3 cụm field — *(intent: `initialMessage` + `title` + user prompts)*, *(action: `tool_use.name` + `tool_use.input` + `parent_tool_use_id`)*, *(feedback: pivot/repeat phát hiện qua CẤU TRÚC turn — `repeat` = chạy lại cùng tool trong cửa sổ, `pivot` = user bẻ hướng tool — không dựa keyword nên độc lập ngôn ngữ)*. Ba cụm này đủ để LLM-judge phát hiện pattern lặp, xác định bước thừa, và đề xuất Skill rõ trigger + steps + preset cá nhân.