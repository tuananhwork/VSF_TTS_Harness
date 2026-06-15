---
name: test-and-report-ci-to-teams
description: "When the user wants to check/run a project's tests and report CI status into the Teams app (personal account) via desktop control. Dùng khi: Khi user muốn kiểm tra/chạy test một dự án rồi báo cáo trạng thái CI vào app Teams (tài khoản cá nhân) qua thao tác desktop."
metadata:
  skill_type: process_macro
  behavior_class: process
  generated_by: pattern-mvp
  generated_on: 2026-06-15
  risk_flags: "none (note: posting to Teams is an outward write action — verify-before-send step is built into the flow)"
---

# test-and-report-ci-to-teams

## Khi nào dùng / When to use

- **VI:** Khi user muốn kiểm tra/chạy test một dự án rồi báo cáo trạng thái CI vào app Teams (tài khoản cá nhân) qua thao tác desktop.
- **EN:** When the user wants to check/run a project's tests and report CI status into the Teams app (personal account) via desktop control.

Triggers / câu kích hoạt thường gặp:
- "chạy test rồi báo CI/CD vào Teams personal"
- "kiểm tra dự án X, gửi trạng thái test vào Teams tài khoản cá nhân"
- "báo cáo CI vào Teams đang mở sẵn, đừng mở từ terminal"

## Tổng quan / Overview

Đây là một **process macro** gồm 4 bước: (1) chuẩn bị & hiểu dự án, (2) chạy test / thu thập trạng thái CI, (3) báo cáo vào Teams qua desktop control, (4) xác minh đã gửi. Không có MCP connector cho Teams cá nhân, nên bước báo cáo dùng **computer-use** (mở app Teams trên máy, dán nội dung, gửi). Vì gửi tin nhắn Teams là hành động ra ngoài (outward write), **luôn xác minh nội dung đã dán trước khi nhấn Enter**.

## Các bước / Steps (ordered flow 1 → 2 → 3 → 4)

### Bước 1 — Chuẩn bị & hiểu dự án / Prepare & understand the project
1. `mcp__cowork__request_cowork_directory` — xin quyền truy cập thư mục dự án (đường dẫn user đưa).
2. `ToolSearch` — nạp các tool cần: `TaskCreate`, `TaskUpdate`, `mcp__mcp-registry__search_mcp_registry`.
3. `mcp__mcp-registry__search_mcp_registry` (keywords: `teams`, `chat`, `messages`) — kiểm tra có connector Teams không. **Theo evidence: không có → sẽ dùng desktop control.**
4. `mcp__workspace__bash` — khảo sát dự án: `ls`, `git log --oneline -5`, `git branch --show-current`, `git remote -v`; đọc `pyproject.toml`/`package.json`/`README`/`AGENTS.md`; tìm harness CI có sẵn (vd `_ci_check/run_checks.bat`) hoặc lệnh test.
5. `TaskCreate` ×4 — tạo 4 task: *Inspect project*, *Run tests/CI*, *Send to Teams*, *Verify delivery*.
6. `AskUserQuestion` — hỏi **2 điều không tự suy ra được**:
   - **Teams đích:** self-chat ("Ghi chú"/chat với chính mình — mặc định an toàn nhất) / một người-chat cụ thể / một channel-team.
   - **Cách chạy test:** chạy lại harness trên máy (khuyến nghị, kết quả mới) / dùng kết quả CI gần nhất.

### Bước 2 — Chạy test / thu thập trạng thái CI / Run tests & collect CI status
1. `mcp__computer-use__request_access` — xin quyền `File Explorer` + `Microsoft Teams`, đặt `clipboardWrite: true`.
2. Chạy checks (ưu tiên harness của dự án):
   - **Cách A (deterministic, khuyến nghị):** chạy `scripts/collect_ci_status.py <project_dir>` → tự chạy `_ci_check/run_checks.bat` nếu có, hoặc pytest / `npm test`, kèm git commit/branch/remote và kiểm tra `gh`. In ra **một block báo cáo sẵn để dán**.
   - **Cách B (desktop, như evidence):** mở File Explorer (`ctrl+l` → gõ đường dẫn `_ci_check` → Enter), double-click `run_checks.bat`, `wait`, rồi **poll file output** (`done.flag`, `pytest.txt`, …).
3. ⚠️ **Cảnh báo cache mount:** poll qua `mcp__workspace__bash` có thể đọc mtime cũ (stale). Nếu `done.flag` có vẻ chưa đổi, chụp `screenshot` để xác nhận console đã chạy xong rồi mới `stat`/đọc lại.
4. Thu thập kết quả: pass/fail + số test + thời gian, import/lint, release CLI, Python/Node version, commit/branch/remote. Nếu **không có `gh`** → báo rõ "chỉ local checks, thiếu trạng thái GitHub Actions".

### Bước 3 — Báo cáo vào Teams / Report into Teams (desktop control)
1. `mcp__computer-use__open_application` (`Microsoft Teams`). Nếu user yêu cầu "dùng Teams đang mở sẵn, đừng mở từ terminal" → chỉ đưa cửa sổ Teams lên, **không** khởi chạy lại từ shell.
2. `screenshot` — **xác nhận đúng đoạn chat đích** (vd self-chat "… (You)" nơi các báo cáo CI trước được đăng). Sai chỗ thì điều hướng tới đúng người/channel user đã chọn.
3. `write_clipboard` — nạp nội dung báo cáo (block từ bước 2; dùng emoji ✅/⚠️/ℹ️ + commit/branch).
4. `left_click` vào ô soạn tin → `key ctrl+v` để dán (Teams: **Enter = gửi, Shift+Enter = xuống dòng** → phải dán cả khối qua clipboard, không gõ từng dòng kèm Enter).
5. **VERIFY-BEFORE-SEND (bắt buộc):** `screenshot` xác nhận nội dung đã dán đúng & đúng đoạn chat. Chỉ khi đúng mới `key Return` để gửi. Đây là điểm side-effect ra ngoài — không nhấn gửi trước khi xác minh.

### Bước 4 — Xác minh đã gửi / Verify delivery
1. `screenshot` — xác nhận tin đã xuất hiện trong đoạn chat và ô soạn đã trống.
2. `TaskUpdate` — đóng các task.
3. Tóm tắt cho user: kết quả CI + chính xác đã gửi vào đâu; nếu thiếu `gh`, đề xuất cài để lấy trạng thái GitHub Actions, hoặc lập lịch chạy báo cáo định kỳ.

## Quick reference

| Việc | Tool chính |
|------|-----------|
| Xin thư mục dự án | `mcp__cowork__request_cowork_directory` |
| Tìm connector Teams | `mcp__mcp-registry__search_mcp_registry` |
| Khảo sát + chạy test | `mcp__workspace__bash`, `scripts/collect_ci_status.py` |
| Xin quyền desktop | `mcp__computer-use__request_access` (clipboardWrite) |
| Mở app / điều hướng | `open_application`, `key`, `left_click`, `screenshot` |
| Dán & gửi | `write_clipboard` → `ctrl+v` → (verify) → `Return` |

## Điểm chưa tốt lần trước / Past pitfalls

- **Mount cache stale:** `bash stat done.flag` báo "chưa xong" dù script đã chạy — phải xác nhận bằng screenshot (gây 5 retry ở evidence session 1).
- **Thiếu `gh` CLI:** không lấy được GitHub Actions từ xa → báo cáo chỉ có local; phải nói rõ giới hạn này.
- **Không có MCP Teams cá nhân:** bắt buộc desktop control; tôn trọng yêu cầu "dùng Teams đang mở sẵn".
- **Enter gửi sớm:** Teams gửi ngay khi Enter — đừng gõ nội dung nhiều dòng trực tiếp; dán qua clipboard rồi verify.

## Evidence

Skill được rút từ các session sau (xem `data/sessions_*/`):

- `local_9590c9ea-0194-4cba-83e3-b4cfe158b151`
- `local_c740302f-169d-480f-9db6-db907ab210c0`
- `local_902a32c7-7c3a-4c11-8b55-cbaf104b102d`

## Risk flags

_None khai báo._ Lưu ý: gửi tin vào Teams là **outward write action** — bước 3.5 (verify-before-send) là bắt buộc trước mọi lần nhấn gửi.
