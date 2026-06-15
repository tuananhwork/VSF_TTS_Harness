---
name: attach-to-running-desktop-app
description: "When operating a desktop app (Teams) to report: attach to the already-open window, do NOT relaunch from terminal — lesson from repeated user corrections. Dùng khi: Khi cần thao tác trên một app desktop (Teams) để báo cáo: dùng cửa sổ app đang mở sẵn trên máy, KHÔNG khởi chạy lại từ terminal — bài học từ việc user phải sửa lại nhiều lần."
metadata:
  skill_type: improvement_lesson
  behavior_class: inefficient
  generated_by: pattern-mvp
  generated_on: 2026-06-15
  risk_flags: "none"
---

# attach-to-running-desktop-app

## Khi nào dùng / When to use

- **VI:** Khi cần thao tác trên một app desktop (Teams) để báo cáo: dùng cửa sổ app đang mở sẵn trên máy, KHÔNG khởi chạy lại từ terminal — bài học từ việc user phải sửa lại nhiều lần.
- **EN:** When operating a desktop app (Teams) to report: attach to the already-open window, do NOT relaunch from terminal — lesson from repeated user corrections.

Triggers / câu kích hoạt thường gặp:
- "dùng Teams **đang mở sẵn**, đừng mở từ terminal"
- "đừng khởi chạy lại app, app đang chạy rồi"
- "sao lại mở cửa sổ Teams mới?" (user phải sửa)
- Bất kỳ tác vụ desktop-control nào trên một app GUI mà user đang để mở (Teams, Slack, browser…).

## Bài học cốt lõi / Core lesson

**Điểm chưa tốt lần trước (what went wrong):** Khi cần báo cáo vào Teams, agent gọi `open_application` / khởi chạy app từ shell/terminal **mà chưa kiểm tra app đã mở sẵn chưa**. Hậu quả: bật ra **cửa sổ/instance mới** (đôi khi màn hình đăng nhập trống, hoặc tách khỏi đoạn chat user đang xem), sai ngữ cảnh, và **user phải sửa lại nhiều lần** ("dùng cái đang mở sẵn"). Đây là hành vi **inefficient** — đốt lượt thao tác, không phá hỏng dữ liệu nhưng làm chậm và gây khó chịu.

**Quy tắc rút ra:** *Attach trước, launch sau.* App GUI mà user đang mở là **nguồn chân lý** — đưa đúng cửa sổ đó lên foreground; chỉ khởi chạy mới khi app **thực sự** chưa chạy.

## Làm gì TRƯỚC tiên lần sau / Do this FIRST next time

> Trước **mọi** lệnh mở app, làm bước 0 này:

1. **`screenshot` trước tiên.** Quan sát desktop/taskbar: Teams đã chạy chưa? Cửa sổ nào đang ở đoạn chat đích?
2. **Nếu đã chạy → ATTACH, không launch.** Đưa cửa sổ hiện có lên foreground bằng cách focus nó (click icon trên taskbar / `alt+tab` / click vào cửa sổ), **không** gọi lệnh launch từ terminal/shell.
3. **Chỉ launch khi thật sự chưa chạy.** Nếu screenshot xác nhận app không mở → khi đó mới `open_application`. Vẫn ưu tiên cơ chế "focus-or-start" thay vì spawn instance mới.
4. **Xác nhận đúng cửa sổ + đúng đoạn chat** bằng một `screenshot` nữa rồi mới thao tác (dán/gửi).

## Flow hỗ trợ / Supporting flow (context)

Bài học này nằm trong bước "Báo cáo vào Teams" của quy trình test → report (xem skill `test-and-report-ci-to-teams`). Vị trí áp dụng:

1. Đã có nội dung báo cáo trong clipboard.
2. **(Bài học)** `screenshot` → phát hiện Teams đang mở → focus cửa sổ đó (đừng relaunch).
3. `left_click` vào ô soạn → `ctrl+v` để dán.
4. `screenshot` verify đúng nội dung & đúng đoạn chat → `Return` để gửi.

## Red flags — DỪNG, bạn đang lặp lại lỗi cũ

- "Để mình mở Teams cho chắc" → **STOP.** Screenshot trước; nó có thể đã mở.
- Sắp gọi `open_application` / chạy lệnh launch **mà chưa screenshot** → STOP.
- Thấy màn hình đăng nhập / cửa sổ trống sau khi "mở" → bạn vừa spawn instance mới; quay lại attach cửa sổ cũ.
- User đã từng nói "dùng cái đang mở" trong session này → **không bao giờ** relaunch nữa.

## Quick reference

| Tình huống | Làm đúng |
|------------|----------|
| Chưa biết app mở chưa | `screenshot` **trước** mọi thứ |
| App đang mở | Focus cửa sổ hiện có (taskbar / `alt+tab`), KHÔNG launch |
| App chưa mở | Khi đó mới `open_application` (ưu tiên focus-or-start) |
| Sau khi attach | `screenshot` xác nhận đúng cửa sổ + đúng đoạn chat |

## Evidence

Skill được rút từ các session sau (xem `data/sessions_*/`):

- `local_902a32c7-7c3a-4c11-8b55-cbaf104b102d`
- `local_c740302f-169d-480f-9db6-db907ab210c0`

## Risk flags

_None khai báo._ Hành vi cốt lõi (focus cửa sổ đang mở) **không phải** side-effect — đây là tối ưu thao tác để tránh relaunch thừa. Việc gửi tin Teams (side-effect ra ngoài) thuộc skill `test-and-report-ci-to-teams` và đã có bước verify-before-send riêng ở đó.
