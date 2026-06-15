# Golden tests — write-short-prd

Ba test case rút từ evidence sessions. Mỗi case kiểm tra một nhánh khác nhau của
flow 1→4 trong `SKILL.md`. "Pass" = agent đi đúng nhánh và giao đúng dạng đầu ra.

---

## Test 1 — Yêu cầu mơ hồ, nhiều hướng → PHẢI hỏi scope + định dạng

**Nguồn / Evidence:** `local_2fc0fafb-26a4-4eb9-83e6-d201ce23199e` (YAML→testcase UI/UX mobile),
củng cố bởi `local_69da99fc-6485-...` (export Excel).

**Input (user):**
> "Tạo prd ngắn gọn cho bài toán: xây dựng testcase từ yaml để test UIUX mobile app"

**Kỳ vọng / Expected:**
1. **Bước 1:** Gọi `AskUserQuestion` với 2 câu — (a) Phạm vi (engine tự build / chuẩn YAML+quy trình / cả hai), (b) Định dạng (chat / `.md` / `.docx`). KHÔNG viết PRD trước khi hỏi.
2. **Bước 3:** Soạn PRD theo khung (Bối cảnh & mục tiêu → phạm vi → yêu cầu chức năng → metric → lộ trình). Nếu user chọn file → `Write` vào `outputs/PRD_<slug>.md`.
3. **Bước 4:** Vì PRD chứa block ```yaml``` → validate parse (chạy `scripts/validate_prd_codeblocks.py` hoặc workspace bash) TRƯỚC khi giao; rồi `present_files`; rồi tóm tắt + **flag quyết định mở** (chọn engine, chiến lược baseline ảnh).

**Fail nếu:** viết thẳng PRD khi yêu cầu còn nhập nhằng; bỏ qua câu hỏi định dạng; giao PRD có YAML chưa kiểm cú pháp.

---

## Test 2 — Yêu cầu rõ & hẹp → trả lời gọn trong chat, không bắt buộc hỏi

**Nguồn / Evidence:** `local_58a12280-1630-4541-a772-71b2f05f241c` (dark mode web app).

**Input (user):**
> "Viết PRD ngắn cho tính năng: dark mode cho web app"

**Kỳ vọng / Expected:**
1. **Bước 1:** Yêu cầu đã rõ và hẹp → có thể bỏ câu hỏi, mặc định render PRD **trực tiếp trong chat**; nêu rõ giả định scope ở đầu (vd chỉ light/dark, không custom theme).
2. **Bước 3:** PRD ngắn với Non-goals rõ ràng (không làm theme tùy chỉnh màu), yêu cầu chức năng cốt lõi (toggle, "theo hệ thống" qua `prefers-color-scheme`, lưu lựa chọn).
3. Không tạo file thừa, không gọi `present_files` (vì là chat).

**Fail nếu:** hỏi lan man dù yêu cầu đã rõ; tạo file khi user không yêu cầu; PRD thiếu mục Non-goals/phạm vi.

---

## Test 3 — Yêu cầu xuất file → Write outputs + present_files + đề xuất follow-up

**Nguồn / Evidence:** `local_1ad3485a-e559-49cb-ba67-90c5f9b5882b` (app nhắc lịch uống nước).

**Input (user):**
> "Viết PRD ngắn cho ý tưởng: app nhắc lịch uống nước" — (ngữ cảnh: user muốn nhận file để chia sẻ)

**Kỳ vọng / Expected:**
1. **Bước 3 (nhánh file):** `Write` PRD vào `<session>/outputs/PRD_<slug>.md` với khung đầy đủ (Tóm tắt → Vấn đề → yêu cầu → chỉ số thành công → cột mốc ~6 tuần).
2. **Bước 4:** `mcp__cowork__present_files` để mở file; KHÔNG có code nhúng nên bỏ qua validate.
3. Kết bằng tóm tắt ngắn + **đề xuất follow-up cụ thể** (chuyển sang Word/PDF, đào sâu logic nhắc nhở hoặc wireframe).

**Fail nếu:** in toàn bộ PRD dài trong chat thay vì giao file khi user muốn file; quên `present_files`; kết thúc lửng không mời bước tiếp theo.

---

## Ghi chú vận hành / Notes

- Không có `risk_flags`. Hành vi side-effect duy nhất là ghi **một** file PRD vào `outputs/`
  — write nhẹ, do user yêu cầu, và scope/định dạng đã được chốt ở Bước 1 nên không cần bước confirm riêng.
- Tín hiệu xanh chung cho cả 3 test: PRD **ngắn, có khung nhất quán**, và luôn **đóng bằng lời mời follow-up / nêu quyết định mở**.
