# Playbook thu log thử nghiệm từ Claude Cowork

Mục tiêu: tạo một bộ session log Cowork **đủ tín hiệu** để pipeline `scan → judge → synth`
sinh ra được cả `process_macro` lẫn `improvement_lesson` — thay vì log đẹp nhưng pipeline
loại sạch.

> Vì sao phải có playbook: ba ràng buộc trong code quyết định log "dùng được" hay không —
> recurrence guard ≥2 session (`scripts/_lib/candidate_schema.py:44`), phân loại 2 skill_type
> (`README.md:57`), và heuristic feedback tiếng Việt (`scripts/scan.py:34`). Checklist này
> ép log chạm đủ cả ba.

---

## Nguyên tắc bất biến (đọc trước khi chạy)

- [ ] **Mỗi task chạy ≥ 3 session riêng biệt** (mở chat MỚI mỗi lần). < 2 session ⇒ bị
      `recurrence_guard` loại, không bao giờ ra skill.
- [ ] **Biến tấu nhẹ input giữa các lần** (đổi file/tên/số liệu) — pattern lặp, không phải copy-paste y hệt.
- [ ] **Dồn các session vào cùng 1 ngày**, hoặc set `TARGET_DATE` trong `scripts/scan.py:27`
      (scan lọc theo cửa sổ ngày).
- [ ] **Đặt tên session/tiêu đề nhất quán theo task** để triage gom đúng cụm.
- [ ] Mỗi task tạo cả **2 vị**: clean run (→ process_macro) và messy run (→ improvement_lesson).

---

## Bảng task mẫu

Chọn 3–4 task đại diện cho việc bạn muốn pipeline học. Gợi ý khởi đầu:

| #   | Task mẫu                              | Tiêu đề session (giữ nhất quán) | Output kỳ vọng (vào `outputs/`) |
| --- | ------------------------------------- | ------------------------------- | ------------------------------- |
| 1   | Làm sạch danh mục vật tư → xuất Excel | `Chuẩn hóa vật tư`              | file `.xlsx`                    |
| 2   | Tổng hợp báo cáo tuần từ nhiều file   | `Báo cáo tuần`                  | file `.md`/`.docx`              |
| 3   | Soạn email theo template              | `Email mẫu`                     | file `.txt`/`.md`               |

> Thay bằng task thật của phòng ban bạn nếu có — pipeline càng sát nghiệp vụ thật càng có giá trị.

---

## Kịch bản cho MỖI task

### A. Clean runs — để test nhánh `process_macro` (chạy 2 lần)

- [ ] Mở chat mới, đặt tiêu đề đúng theo bảng.
- [ ] Mô tả task gọn, đủ ngữ cảnh ngay từ prompt đầu.
- [ ] Để Claude làm liền mạch; **xác nhận bằng đúng cụm** heuristic confirm bắt được:
      `ok`, `đúng rồi`, `tiếp tục`, `chính xác`, `ngon` (xem `scripts/scan.py:39`).
- [ ] Đảm bảo có **file thật ra `outputs/`** (đếm vào `outputs_produced`).
- [ ] Lần 2: lặp lại với input biến tấu nhẹ.

### B. Messy run — để test nhánh `improvement_lesson` (chạy ≥ 1 lần)

- [ ] Mở chat mới, cùng tiêu đề task.
- [ ] **Cố tình để Claude hiểu sai** rồi đính chính bằng đúng cụm correction heuristic bắt:
      `không phải`, `không đúng`, `sai rồi`, `làm lại`, `khoan`, `bỏ qua`, `hủy`
      (xem `scripts/scan.py:34`).
- [ ] Tạo ít nhất một **retry**: yêu cầu lặp lại cùng thao tác/tool trong vòng 60s
      (heuristic retry bắt theo cùng tool + cùng input ≤ 60s, `scripts/scan.py:43`).
- [ ] Mục tiêu: session này có `correction_count > 0` và/hoặc `retry_count > 0`.

> Đây là cách DUY NHẤT để test nhánh correction-heavy. Log toàn "clean" sẽ không bao giờ
> kích hoạt `improvement_lesson`.

---

## Sau khi thu xong — verify trước khi tin kết quả

- [ ] Chạy scan:
      ```bash
      uv run python scripts/scan.py
      ```
- [ ] Mở `data/sessions_<date>_runAt_<ts>/_index.json` → kiểm tra `matched` ≥ số session đã chạy.
- [ ] Mở vài file `*.jsonl`, xác nhận trên record `session_summary`:
      `correction_count` / `confirm_count` / `retry_count` / `outputs_produced` đúng như chủ đích.
      Nếu = 0 hết ⇒ heuristic chưa bắt được, sửa lại cách phát ngôn rồi chạy lại Cowork.
- [ ] Chạy judge:
      ```bash
      uv run python scripts/judge.py --sessions-dir data/sessions_<date>_runAt_<ts> --min-recurrence 2
      ```
- [ ] Kiểm tra theo thứ tự giá trị:
  - [ ] `cluster_summary.json` — triage có gom đúng các session cùng task vào 1 cluster không?
  - [ ] `_raw_extract_*` — flow trích ra có **đúng thứ tự** các bước không?
  - [ ] `candidate_skills.json` — `skill_type` phân loại đúng (clean→process_macro, messy→improvement_lesson)?
  - [ ] `_raw_debate_*` / `_raw_consolidate_*` — đọc để hiểu phán xét, KHÔNG kỳ vọng nó lọc nhiễu (xem cảnh báo dưới).

---

## Lưu ý MVP (đừng hiểu lầm kết quả)

Theo `docs/products/agent-debate.md:57`, MVP chỉ bật **2 judge cùng phe** (Năng suất +
Chất lượng). Hệ quả: debate **chưa** loại được "pattern tốt nhưng không đáng đóng gói" —
bộ lọc nhiễu thật vẫn là `recurrence_guard`. Khi đánh giá log thử nghiệm, hãy chấm pipeline
trên 3 việc: (a) recurrence gom đúng, (b) extract trích đúng flow có thứ tự, (c) skill_type
phân loại đúng. Đừng kết luận "debate vô dụng" — Cost/Business judge đang pending mới là phần
mở khóa giá trị phản biện.

---

## Định mức tối thiểu cho 1 buổi thử nghiệm "đủ"

3 task × (2 clean + 1 messy) = **9 session trong 1 ngày**. Đây là mức tối thiểu để:
- mỗi task qua được recurrence ≥2, và
- có dữ liệu cho cả hai nhánh skill_type.
