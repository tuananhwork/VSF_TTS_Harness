---
name: write-short-prd
description: "When the user asks for a short PRD for a feature/idea/problem (clarify scope, then produce the PRD file). Dùng khi: Khi user yêu cầu viết PRD ngắn gọn cho một feature/ý tưởng/bài toán (hỏi làm rõ scope rồi xuất file PRD)."
metadata:
  skill_type: process_macro
  behavior_class: process
  generated_by: pattern-mvp
  generated_on: 2026-06-15
  risk_flags: "none (note: ghi 1 file PRD vào thư mục outputs/ của session — write nhẹ, do user yêu cầu; scope & định dạng đã được xác nhận qua AskUserQuestion trước khi ghi)"
---

# write-short-prd

## Khi nào dùng / When to use

- **VI:** Khi user yêu cầu viết PRD ngắn gọn cho một feature/ý tưởng/bài toán (hỏi làm rõ scope rồi xuất file PRD).
- **EN:** When the user asks for a short PRD for a feature/idea/problem (clarify scope, then produce the PRD file).

Triggers / câu kích hoạt thường gặp:
- "Viết PRD ngắn cho tính năng: …" / "Write a short PRD for feature: …"
- "Viết PRD ngắn cho ý tưởng: …" / "PRD ngắn cho bài toán: …"
- "Tạo prd ngắn gọn cho …" (kèm hoặc không kèm yêu cầu xuất file)

## Tổng quan / Overview

Đây là một **process macro** 4 bước: (1) làm rõ scope + chọn định dạng đầu ra, (2) (tùy độ lớn) lập task để theo dõi, (3) soạn PRD ngắn theo khung cố định, (4) kiểm tra & giao kết quả. Mục tiêu là một PRD **ngắn, đủ để quyết định** — không phải đặc tả dày. Điểm mấu chốt rút từ evidence: **hỏi làm rõ scope + định dạng TRƯỚC khi viết** khi yêu cầu còn mơ hồ, và **mở file ra cho user bằng `present_files`** khi xuất file.

## Các bước / Steps (ordered flow 1 → 2 → 3 → 4)

### Bước 1 — Làm rõ scope & chọn định dạng / Clarify scope & pick output format
1. Đọc yêu cầu. Nếu **bài toán mơ hồ hoặc có nhiều hướng** (ví dụ "tool YAML→testcase" có thể là engine, là format, hoặc cả hai) → `AskUserQuestion` với **2 câu** (theo evidence):
   - **Phạm vi / Scope:** hướng nào của feature (1 lựa chọn hoặc multi-select các mảng cần có).
   - **Định dạng đầu ra / Format:** `Trả lời trong chat (markdown)` · `File Markdown (.md)` · `File Word (.docx)`.
2. Nếu yêu cầu **đã rõ và hẹp** (ví dụ "dark mode cho web app") → bỏ qua câu hỏi, mặc định trả lời gọn trong chat, và **vẫn nói rõ giả định về scope** ở đầu PRD.
3. Quy tắc chọn nhanh: chưa nói gì về file → ưu tiên hỏi; user nói "xuất file/giao file" → đi thẳng vào nhánh file (.md là mặc định gọn nhẹ).

### Bước 2 — (Tùy chọn) Lập task theo dõi / Optionally set up tasks
1. Chỉ làm khi PRD lớn/nhiều phần (như session YAML-testcase). `ToolSearch` (`select:TaskCreate,TaskUpdate`) để nạp tool.
2. `TaskCreate` ×2: *Viết PRD* và *Rà soát & xuất file*; `TaskUpdate` → `in_progress` khi bắt đầu.
3. PRD đơn giản (dark mode, app nhắc uống nước) → bỏ qua bước này, viết thẳng.

### Bước 3 — Soạn PRD ngắn / Draft the short PRD
Dùng khung cố định (giữ NGẮN — mỗi phần vài dòng):
- **Header:** Tiêu đề · Tác giả/Owner · Ngày · Phiên bản · Trạng thái (Draft/Đề xuất).
- **1. Bối cảnh & Vấn đề** — ai đau ở đâu, vì sao đáng làm.
- **2. Mục tiêu & Non-goals** — kết quả mong muốn + nói rõ cái KHÔNG làm ở V1 (out of scope).
- **3. Yêu cầu chức năng** — đánh số 3.1, 3.2…; chỉ những gì cốt lõi.
- **4. Chỉ số thành công** — đo bằng gì (metric).
- **5. Lộ trình / Milestones** — phase ngắn (vd 3 phase / 6 tuần).
- **6. Câu hỏi mở / Quyết định cần sớm** — liệt kê điểm còn phải chốt.

Nhánh xuất file: `Write` vào `<session>/outputs/PRD_<slug>.md` (slug từ tên feature). Nhánh chat: render trực tiếp khung trên.

### Bước 4 — Kiểm tra & giao / Verify & deliver
1. **Nếu PRD có code/spec nhúng** (YAML/JSON schema, ví dụ cấu hình) → kiểm tra nó parse được trước khi giao. Dùng `scripts/validate_prd_codeblocks.py <file.md>` (hoặc `mcp__workspace__bash` chạy parser như evidence session 2fc0fafb). Không có code nhúng → bỏ qua.
2. Nhánh file: `mcp__cowork__present_files` để mở file PRD cho user; `TaskUpdate` → `completed` các task.
3. Tóm tắt ngắn: nội dung chính + **nêu rõ các quyết định còn mở** (vd "chọn engine", "chiến lược baseline") và **chủ động đề xuất follow-up** (chuyển sang Word/PDF, đào sâu một phần, vẽ wireframe).

## Quick reference

| Việc | Tool chính |
|------|-----------|
| Hỏi scope + định dạng | `AskUserQuestion` (2 câu: Phạm vi, Định dạng) |
| (Tùy) lập task | `ToolSearch` → `TaskCreate` ×2 → `TaskUpdate` |
| Ghi file PRD | `Write` → `<session>/outputs/PRD_<slug>.md` |
| Kiểm tra code nhúng | `scripts/validate_prd_codeblocks.py` / `mcp__workspace__bash` |
| Mở file cho user | `mcp__cowork__present_files` |

## Cách làm tốt / What works

- **Hỏi đúng 2 thứ, không hỏi lan man:** scope + định dạng đủ để bắt đầu (evidence 69da99fc, 2fc0fafb).
- **Giữ PRD ngắn & có khung nhất quán** — header meta + 5–6 mục; ai cũng đọc nhanh ra quyết định.
- **Xuất file thì phải `present_files`** rồi mới tóm tắt — user thấy ngay (evidence 1ad3485a, 2fc0fafb).
- **Chủ động flag quyết định mở & đề xuất bước tiếp** thay vì kết thúc lửng (cả 4 session đều đóng bằng lời mời follow-up).

## Điểm chưa tốt lần trước / Past pitfalls

- **Lao vào viết khi yêu cầu mơ hồ:** với bài toán nhiều hướng (engine vs format), bỏ qua AskUserQuestion dễ viết sai trọng tâm → luôn hỏi 2 câu khi còn nhập nhằng.
- **Quên định dạng:** viết file khi user chỉ muốn câu trả lời trong chat (hoặc ngược lại) — hỏi format ngay từ đầu.
- **Code nhúng không kiểm:** PRD có YAML/JSON mà không validate dễ giao spec sai cú pháp — luôn parse trước khi giao (Bước 4.1).
- **PRD phình dài:** mục tiêu là "ngắn, đủ quyết định"; cắt chi tiết triển khai, để dành cho follow-up.

## Evidence

Skill được rút từ các session sau (xem `data/sessions_*/`):

- `local_69da99fc-6485-427f-ac53-76afd677467c`
- `local_58a12280-1630-4541-a772-71b2f05f241c`
- `local_1ad3485a-e559-49cb-ba67-90c5f9b5882b`
- `local_2fc0fafb-26a4-4eb9-83e6-d201ce23199e`

## Risk flags

_None khai báo._ Lưu ý: bước 3 ghi **một** file PRD vào `outputs/` của session — write nhẹ, do user yêu cầu ("xuất file PRD"); scope & định dạng đã được xác nhận qua `AskUserQuestion` (Bước 1) trước khi ghi. Không xóa/ghi đè file ngoài outputs.
