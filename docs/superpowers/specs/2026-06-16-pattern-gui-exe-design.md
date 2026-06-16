# Design Spec — Pattern GUI (.exe)

| Field | Value |
|-------|-------|
| Ngày | 2026-06-16 |
| Tác giả | Tuan Anh + Claude |
| Trạng thái | Draft — chờ review |

---

## 1. Mục tiêu

Đóng gói pipeline Pattern (Scan → Judge → Synth → Accept) thành một file `Pattern.exe` cho Windows. User không cần terminal, không cần Python, không cần clone code — chỉ cần double-click và chọn ngày.

**Non-goals:**
- Cross-platform (macOS/Linux) — để sau
- Auto-update
- Multi-user / server mode

---

## 2. Tiền đề môi trường

| Thứ | Có sẵn? | Ghi chú |
|-----|---------|---------|
| Claude Desktop | ✅ | Log nguồn chính |
| Claude Code CLI (`claude`) | ✅ | Dùng làm LLM subprocess cho bước Synth |
| Python / uv | ❌ | Không cần — bundled trong .exe |

Bước Synth gọi `claude` CLI qua subprocess. Nếu `claude` không có trên PATH, app hiển thị lỗi rõ ràng.

---

## 3. Architecture

```
Pattern.exe (PyInstaller bundle)
├── gui/
│   ├── app.py          # CustomTkinter app + 3 màn hình
│   └── pipeline_runner.py  # chạy pipeline trong background thread
└── scripts/ + scripts/_lib/  # pipeline code hiện tại, import trực tiếp
```

**Luồng dữ liệu:**

```
[GUI thread]                    [Pipeline thread]
     │                                │
     │── start_pipeline(params) ─────►│
     │                                │ scan() → sessions_dir
     │◄── log("Scan ✓") ─────────────│
     │                                │ judge() → candidate_skills.json
     │◄── log("Judge ✓") ────────────│
     │                                │ synth() → proposal/
     │◄── log("Synth ✓") ────────────│
     │◄── proposals(list[Skill]) ─────│
     │                                │
     │ [User chọn skill]              │
     │── accept(selected) ───────────►│
     │                                │ copy to ~/.claude/skills/
     │◄── done() ─────────────────────│
```

GUI thread và pipeline thread giao tiếp qua `queue.Queue` — không block UI.

---

## 4. GUI — 3 màn hình

### 4.1 Configure

```
┌─────────────────────────────────────────┐
│  🔍 Pattern                        [─][□][×]│
├─────────────────────────────────────────┤
│                                         │
│  Ngày phân tích                         │
│  [  2026-06-16  ] [📅]                  │
│                                         │
│  Nguồn log                              │
│  ( ) claude-cowork  (•) claude-code     │
│                                         │
│  ▶ Tuỳ chọn nâng cao                   │
│  ┌───────────────────────────────────┐  │
│  │ Min recurrence   [2]  ▲▼          │  │
│  │ Max deepdive     [5]  ▲▼          │  │
│  └───────────────────────────────────┘  │
│                                         │
│         [    Chạy Pipeline    ]         │
└─────────────────────────────────────────┘
```

- Date picker: text input + calendar popup. Default = hôm nay.
- Advanced: collapsed mặc định, toggle bằng click.
- Nút "Chạy Pipeline": chuyển sang màn hình Running.

### 4.2 Running

```
┌─────────────────────────────────────────┐
│  🔍 Pattern                        [─][□][×]│
├─────────────────────────────────────────┤
│                                         │
│  ● Scan      ✓ Xong                    │
│  ● Judge     ⏳ Đang chạy...           │
│  ● Synth     ○ Chờ                     │
│                                         │
│  ─────────────────────────────────────  │
│  [log output area — scrollable]         │
│  > Scanning 2026-06-16...               │
│  > Found 4 sessions                     │
│  > Running judge...                     │
│                                         │
│                                         │
│  [  Huỷ  ]            [ Copy log 📋 ]  │
└─────────────────────────────────────────┘
```

- Mỗi bước (Scan / Judge / Synth) có icon trạng thái: ○ chờ / ⏳ đang / ✓ xong / ✗ lỗi.
- Log area nhận message real-time qua `log_fn` callback từ pipeline thread (không phải subprocess stdout).
- Lỗi highlight đỏ. Nút "Copy log" để user gửi IT debug.
- Tự động chuyển sang màn hình Review khi Synth xong.

### 4.3 Review & Accept

```
┌─────────────────────────────────────────┐
│  🔍 Pattern                        [─][□][×]│
├─────────────────────────────────────────┤
│  Phát hiện 3 skill. Chọn để cài:       │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ ☑  run-ci-report                │    │
│  │    "Chạy CI và gửi kết quả"     │    │
│  │    Lặp 5 lần • Độ tin cậy: cao  │    │
│  ├─────────────────────────────────┤    │
│  │ ☑  check-teams-running          │    │
│  │    "Kiểm tra Teams trước khi..."│    │
│  │    Lặp 3 lần • Độ tin cậy: TB  │    │
│  ├─────────────────────────────────┤    │
│  │ ☐  write-short-prd              │    │
│  │    "Viết PRD ngắn từ ý tưởng"   │    │
│  │    Lặp 2 lần • Độ tin cậy: thấp│    │
│  └─────────────────────────────────┘    │
│                                         │
│  [  ← Quay lại  ]  [ Cài skill đã chọn ]│
└─────────────────────────────────────────┘
```

- Mỗi skill hiển thị: tên, mô tả ngắn, số lần lặp, độ tin cậy.
- Checkbox để chọn/bỏ.
- "Cài skill đã chọn": copy folder vào `~/.claude/skills/<name>/`, hiển thị toast "Đã cài X skill. Có hiệu lực phiên Claude tiếp theo."
- "Quay lại": về Configure để chạy ngày khác.

---

## 5. Pipeline Integration

Scripts hiện tại (`scan.py`, `judge.py`, `synth.py`) được **import trực tiếp** như Python modules, chạy trong background thread — không gọi subprocess riêng cho từng bước.

```python
# pipeline_runner.py (sketch)
from scripts.scan import run_scan
from scripts.judge import run_judge
from scripts.synth import run_synth

def run_pipeline(params, log_queue):
    sessions_dir = run_scan(params.date, params.source, log_fn=log_queue.put)
    candidates   = run_judge(sessions_dir, log_fn=log_queue.put)
    proposals    = run_synth(candidates, log_fn=log_queue.put)
    return proposals
```

**Yêu cầu refactor nhỏ trên scripts hiện tại:**
- Tách logic vào hàm `run_<step>(params, log_fn)` riêng; `@click.command` gọi hàm đó — tránh việc PyInstaller không thể call click-decorated function trực tiếp khi import.
- Thay `print()` bằng callback `log_fn(msg)` — CLI vẫn pass `print` làm default.
- Scripts CLI giữ nguyên hoạt động qua `uv run`.
- `sys.path.insert` trong scripts cần được thay bằng package-relative import sau khi cấu trúc thư mục chuyển thành package (thêm `__init__.py` vào `scripts/` và `scripts/_lib/`).

Bước Synth gọi `claude` CLI qua subprocess riêng (như hiện tại trong `_lib/claude_runner.py`). Không thay đổi.

---

## 6. Packaging — PyInstaller

```
pyinstaller --onefile --windowed \
  --name Pattern \
  --icon assets/pattern.ico \
  --add-data "scripts/_lib:scripts/_lib" \
  gui/app.py
```

Output: `dist/Pattern.exe` (~80–120 MB).

Distribution: IT copy file vào Desktop hoặc shared drive. Không cần installer.

**Lưu ý PyInstaller:**
- `--windowed`: không hiện console window.
- `sys._MEIPASS`: dùng để resolve path tới bundled files khi chạy từ .exe.
- `claude` CLI được gọi qua `subprocess` — phải có sẵn trên `PATH` của user.

---

## 7. Error Handling

| Tình huống | Hiển thị |
|------------|----------|
| `claude` không có trên PATH | Dialog: "Chưa tìm thấy Claude Code CLI. Liên hệ IT." |
| Không tìm thấy log Claude Desktop | Dialog: "Không có log ngày này. Thử ngày khác." |
| Synth timeout / LLM error | Bước Synth icon ✗ đỏ, log chi tiết, nút "Copy log" |
| 0 session trong ngày | Màn hình Running: "Không có session nào ngày này." |
| 0 candidate sau Judge | Skip thẳng tới thông báo: "Chưa phát hiện pattern đủ mạnh." |

---

## 8. Cấu trúc thư mục mới

```
Pattern/
├── gui/
│   ├── app.py              # CTk app, điều phối 3 màn hình
│   ├── screen_configure.py
│   ├── screen_running.py
│   ├── screen_review.py
│   └── pipeline_runner.py  # background thread + queue
├── assets/
│   └── pattern.ico
├── scripts/                # không đổi, chỉ refactor main()
│   ├── scan.py
│   ├── judge.py
│   ├── synth.py
│   └── _lib/
├── build_exe.py            # wrapper gọi PyInstaller với đúng flags
└── pyproject.toml          # thêm customtkinter, pyinstaller vào deps
```

---

## 9. Tiêu chí hoàn thành

- [ ] `Pattern.exe` chạy được trên máy Windows không có Python
- [ ] Chọn ngày → chạy full pipeline → cài skill trong 1 luồng không tắt cửa sổ
- [ ] Lỗi hiển thị rõ, không crash thầm lặng
- [ ] Scripts hiện tại (`uv run e2e.py`) vẫn chạy bình thường sau refactor
