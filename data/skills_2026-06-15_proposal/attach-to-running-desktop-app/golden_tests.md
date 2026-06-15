# Golden tests — attach-to-running-desktop-app

Ba test case rút từ evidence sessions. Đây là **improvement_lesson**, nên "Pass" =
agent **attach vào cửa sổ đang mở** thay vì relaunch từ terminal, và làm bước
`screenshot`-trước-tiên trước khi đụng vào app.

---

## Test 1 — Teams đã mở sẵn → PHẢI attach, KHÔNG relaunch

**Nguồn / Evidence:** `local_902a32c7-7c3a-4c11-8b55-cbaf104b102d`
(user phải sửa lại vì agent mở Teams từ terminal).

**Input (user):**
> "Báo cáo trạng thái test vào Teams — **Teams đang mở sẵn rồi, đừng mở lại từ terminal**."

**Kỳ vọng / Expected:**
1. **Bước 0 (bài học):** Gọi `screenshot` TRƯỚC tiên để xác nhận Teams đang chạy và đang ở đoạn chat nào.
2. Đưa **cửa sổ Teams hiện có** lên foreground bằng focus (taskbar / `alt+tab` / click), **không** gọi `open_application` hay lệnh launch từ shell.
3. `screenshot` lần nữa xác nhận đúng cửa sổ + đúng đoạn chat → rồi mới dán/gửi.

**Fail nếu:** gọi `open_application` / chạy lệnh launch trong khi app đã mở; spawn cửa sổ/instance mới; bỏ qua screenshot mở đầu.

---

## Test 2 — Không nói rõ trạng thái app → vẫn screenshot trước, không mặc định launch

**Nguồn / Evidence:** `local_c740302f-169d-480f-9db6-db907ab210c0`
(luồng report CI vào Teams qua desktop control).

**Input (user):**
> "Gửi kết quả CI vào Teams cá nhân giúp mình." *(không nói app đã mở hay chưa)*

**Kỳ vọng / Expected:**
1. **Không mặc định launch.** Gọi `screenshot` để kiểm tra Teams đã chạy chưa.
2. Nếu screenshot cho thấy Teams **đã mở** → attach cửa sổ đó (như Test 1).
3. Chỉ khi screenshot xác nhận Teams **chưa chạy** mới `open_application` (ưu tiên focus-or-start, không spawn trùng).

**Fail nếu:** chạy thẳng lệnh launch khi chưa kiểm tra; mở instance thứ hai dù app đã chạy.

---

## Test 3 — Lỡ relaunch ra cửa sổ trống → tự nhận ra & quay về attach

**Nguồn / Evidence:** `local_902a32c7-7c3a-4c11-8b55-cbaf104b102d` (lặp lại nhiều lần trước khi đúng).

**Input (tình huống):**
> Sau khi agent "mở Teams", `screenshot` cho thấy **màn hình đăng nhập / cửa sổ trống**, không phải đoạn chat user đang dùng.

**Kỳ vọng / Expected:**
1. **Nhận diện red flag:** cửa sổ trống/đăng nhập = vừa spawn instance mới (lỗi cũ).
2. **Khắc phục:** quay lại **focus cửa sổ Teams gốc** đang chạy (taskbar / `alt+tab`), bỏ cửa sổ vừa bật.
3. `screenshot` xác nhận đã về đúng đoạn chat trước khi thao tác tiếp; không lặp lại việc relaunch.

**Fail nếu:** tiếp tục thao tác trên cửa sổ trống/đăng nhập; relaunch thêm lần nữa; không nhận ra đã mở sai instance.

---

## Ghi chú vận hành / Notes

- Không có `risk_flags`. Hành vi cốt lõi (focus cửa sổ đang mở) không phải side-effect
  nên không cần bước confirm; đây là tối ưu thao tác (`behavior_class: inefficient`).
- Tín hiệu xanh chung cho cả 3 test: **`screenshot` luôn đi trước mọi lệnh mở app**, và
  agent **attach** vào cửa sổ đang mở thay vì khởi chạy lại từ terminal.
