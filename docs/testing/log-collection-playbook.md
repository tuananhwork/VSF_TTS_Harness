# Playbook thu log thử nghiệm từ Claude Cowork

Mục tiêu: tạo một bộ session log Cowork **đủ tín hiệu** để pipeline `scan → judge → synth`
sinh ra được cả `process_macro` lẫn `improvement_lesson` — thay vì log đẹp nhưng pipeline
loại sạch.

> Vì sao phải có playbook: ba ràng buộc trong code quyết định log "dùng được" hay không —
> recurrence guard ≥2 session (`scripts/_lib/candidate_schema.py:44`), phân loại 2 skill_type
> (`README.md:57`), và tín hiệu feedback **cấu trúc** (`scripts/scan.py`, không còn keyword).
> Checklist này ép log chạm đủ cả ba.
>
> ⚠️ Khác bản cũ: feedback giờ suy ra từ **hành vi**, không từ câu chữ. Không cần "nói đúng
> cụm từ" nữa — muốn có tín hiệu thì phải tạo ra **hành vi** tương ứng (xem mục B).

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
- [ ] Để Claude làm **liền mạch một hướng** — đừng bắt nó đổi tool giữa chừng (giữ `pivot_rate`
      thấp). Lời lẽ xác nhận nói sao cũng được; không còn dò keyword.
- [ ] Đảm bảo có **file thật ra `outputs/`** (đếm vào `outputs_produced`).
- [ ] Lần 2: lặp lại với input biến tấu nhẹ.

### B. Messy run — để test nhánh `improvement_lesson` (chạy ≥ 1 lần)

Tín hiệu giờ là **cấu trúc**, nên phải tạo ra HÀNH VI, không phải câu chữ:

- [ ] Mở chat mới, cùng tiêu đề task.
- [ ] Tạo **pivot**: để Claude bắt đầu làm theo một hướng tool (vd đang `Read`/`Grep`), rồi
      chen yêu cầu khiến nó **chuyển sang bộ tool khác hẳn** (vd `WebSearch`/`Edit`). Pivot bắt
      khi tập tool *trước* và *sau* lượt user của bạn lệch nhau ≥ 0.5 (Jaccard) — nói bằng ngôn
      ngữ nào cũng được, miễn HƯỚNG TOOL đổi.
- [ ] Tạo **repeat**: khiến Claude **chạy lại cùng một tool** ở lượt sau trong vòng 60s (vd
      lệnh fail rồi nó chạy lại, hoặc bạn yêu cầu thử lại đúng thao tác đó).
- [ ] Mục tiêu: session này có `pivot_count > 0` và/hoặc `repeat_count > 0`.

> Đây là cách DUY NHẤT để test nhánh ma-sát-cao. Log toàn "clean một hướng" sẽ không bao giờ
> kích hoạt `improvement_lesson`. Lưu ý: chỉ "nói sai rồi làm lại" mà KHÔNG đổi hướng tool thì
> **không** tính pivot nữa — đó chính là điểm khác so với bản keyword cũ.

---

## Sau khi thu xong — verify trước khi tin kết quả

- [ ] Chạy scan:
      ```bash
      uv run python scripts/scan.py
      ```
- [ ] Mở `data/sessions_<date>_runAt_<ts>/_index.json` → kiểm tra `matched` ≥ số session đã chạy.
- [ ] Mở vài file `*.jsonl`, xác nhận trên record `session_summary`:
      `pivot_count` / `repeat_count` / `outputs_produced` đúng như chủ đích.
      Nếu = 0 hết ⇒ hành vi chưa tạo đủ tín hiệu (chưa đổi hướng tool / chưa lặp tool), điều
      chỉnh KỊCH BẢN THAO TÁC rồi chạy lại Cowork — không phải sửa câu chữ.
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
