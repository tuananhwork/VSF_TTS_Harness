Để hệ debate hoạt động hiệu quả, các Agent cần hệ giá trị trái ngược hoặc bổ khuyết cho nhau.
Đề xuất: 
1. Judge Năng suất (Efficiency): Phát hiện các chuỗi chat quá dài, thao tác lặp đi lặp lại hoặc bị bấm nút dừng để đề xuất đóng gói giảm bớt bước thủ công.
2. Judge Chất lượng (Quality): Phát hiện những chỗ user phải liên tục sửa sai, đính chính ý định để thiết kế lại prompt chuẩn, đủ ngữ cảnh đầu vào.
3. Judge Chi phí (Cost): Phát hiện việc nhồi nhét file quá tải gây lãng phí token hoặc dùng model đắt cho việc dễ để đề xuất tối ưu chi phí và dùng sub-agent rẻ hơn - Phần này a Hiếu chưa care lắm, nên để pending ở MVP.
4. Judge Nghiệp vụ (Business): Phân biệt luồng làm việc thực tế với việc chat tự học cá nhân, đảm bảo chỉ đóng gói những quy trình cốt lõi có giá trị cho công ty - Chưa có domain cụ thể nên phần này pending.
Debate: 4 Judge trên sẽ phản biện qua lại để loại bỏ nhiễu. Cuối cùng, Agent Consolidator sẽ chốt lại giải pháp tối ưu nhất.

Ví dụ:
1. Judge Năng suất: "Tạo Skill vì Nhân viên mất tận 12 lượt chat chỉ để làm sạch dữ liệu và xuất Excel. Quá tốn thời gian và thao tác thủ công."
2. Judge Chất lượng: "Đồng ý. Nhân viên phải sửa sai 4 lần vì Claude hiểu nhầm cấu trúc cột. Cần một Skill cố định sẵn khung Input/Output để chuẩn hóa ngay từ đầu."
3. Judge Chi phí (MVP - Tạm hoãn): "Phản đối tạo Skill cho cả 12 lượt. Nhân viên paste đi paste lại file dữ liệu thô gây lãng phí token. Nếu tạo Skill, cần ép đẩy phần làm sạch dữ liệu thô qua code xử lý trước, không dùng LLM."
4. Judge Nghiệp vụ (MVP - Tạm hoãn): "Bổ sung ngữ cảnh: Đây là luồng chuẩn hóa danh mục vật tư chuẩn bị đấu thầu. Đây là quy trình cốt lõi, lặp lại hàng tuần của phòng ban này, rất đáng để đóng gói."

CONSOLIDATOR - Quyết nghị: Phê duyệt

---

## Quyết định kiến trúc — ghép vào pipeline judge

Debate **không viết lại pipeline**. Nó thay đúng tầng `deepdive` hiện tại trong
`scripts/judge.py` (cùng bản chất: đọc full trace của 1 candidate rồi phán xét).
Mọi tầng phía trước giữ nguyên: `aggregate → triage(LLM) → recurrence_guard(code)`
là phần gom/lọc rẻ, không đụng.

Pipeline sau khi ghép:

```
aggregate → triage(LLM) → recurrence_guard(code) →
  ┌─ extract (1 call): action_template, golden_tests, good/weak_points   (trích sự thật, trung lập)
  ├─ debate  (N call song song): mỗi judge chỉ chấm trục của mình → {judge, stance, axis_score, argument}
  └─ consolidate (1 call): final_score, rejected_reason, consolidator_note
→ score+sort → render
```

Chi phí mỗi candidate: `1 + N + 1` call. MVP (N=2) ⇒ 4 call/candidate; số candidate
đã bị cap bởi `--max-deepdive` nên tổng vẫn kiểm soát được.

### Vì sao tách "trích xuất" khỏi "phán xét"

`deepdive` cũ làm lẫn 2 việc: (a) trích sự thật từ trace (`action_template`,
`golden_tests`, good/weak points — không có quan điểm) và (b) phán xét
(`final_score`, `rejected_reason`). Debate chỉ có nghĩa ở phần (b). Bắt cả N judge
cùng trích lại template vừa tốn token vừa cho ra N template lệch nhau khó merge.
Nên: extract làm 1 lần (trung lập), mỗi judge chỉ tranh luận + chấm trên đúng trục
của mình, consolidator chốt accept/reject + score.

### Phân vai bộ lọc

- `recurrence_guard` (code, deterministic) — chặn one-off. **Đây là cổng loại nhiễu
  chính ở MVP**, và thực chất là "judge Chi phí phiên bản nghèo": singleton không
  đáng token để đóng gói đã bị chặn miễn phí.
- `triage` — loại sớm `duplicate` / `too_generic` / `not_a_pattern` trước khi tốn 4 call.
- Consolidator — **vẫn được phép bác** (`rejected_reason = "low_score"`) khi cả N judge
  chấm trục thấp. Giữ quyền này, nếu không consolidator chỉ là con dấu cao su.

### Đánh đổi MVP đã chấp nhận có chủ đích

MVP chỉ bật 2 judge **cùng phe** (Năng suất + Chất lượng), đều thiên về "nên đóng gói".
Hệ quả: debate MVP **chưa** loại được "pattern tốt nhưng không đáng đóng gói" — đó
đúng là việc của judge Chi phí (đang pending). Giá trị phản biện thật của debate chỉ
mở khóa khi Cost/Business bật lại. MVP trả tiền cho 4 call/candidate chủ yếu để
**dựng sẵn interface song song + consolidator**, không phải để lọc tốt hơn
`recurrence_guard`. Ghi rõ ở đây để sau này nhìn lại không hiểu lầm "debate không hiệu quả".

### Việc kỹ thuật còn lại

- `run_claude_json` đang sync → bọc `ThreadPoolExecutor` cho phần debate
  (`ccs one -p` là subprocess I/O-bound, thread đủ, không cần async).
- Mỗi judge = 1 block instruction tách rời + 1 entry trong list `JUDGES`.
  Bật Cost/Business về sau = thêm 1 block + 1 phần tử list, không đụng orchestration.
- Schema candidate thêm: `debate: [{judge, stance, axis_score, argument}]`,
  `consolidator_note`. `render_proposal` thêm mục hiển thị debate.
