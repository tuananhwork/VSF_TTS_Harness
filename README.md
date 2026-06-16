# Pattern — Behavior → Skill harness for Claude Cowork

Quan sát hành vi user trên Claude Cowork → đề xuất Skill draft cá nhân hoá.

## Yêu cầu

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Claude Code CLI (`claude`) đã đăng nhập, có trên `PATH`
- Đã có session log Claude Cowork trên máy (tự động tìm — xem bên dưới)

## Chạy toàn bộ pipeline (1 lệnh)

```bash
uv run e2e.py
```

Pipeline sẽ tự động:
1. Cài dependencies (`uv sync`)
2. **Scan** — quét session log Claude hôm nay
3. **Judge** — LLM phân tích pattern hành vi
4. **Synth** — sinh Skill draft
5. **Accept** — chọn Skill muốn cài (interactive)

### Tuỳ chọn

```
--sessions-dir PATH        Bỏ qua bước scan, dùng thư mục sessions có sẵn
--min-recurrence N         Số lần lặp tối thiểu để coi là pattern (mặc định: 2)
--max-deepdive N           Số candidate tối đa đưa vào debate (mặc định: 5)
--llm-provider PROVIDER    'claude' (mặc định) hoặc 'ccs'
--ccs-profile NAME         Tên CCS profile (bắt buộc khi dùng --llm-provider=ccs)
```

Ví dụ:

```bash
# Dùng CCS thay vì Claude trực tiếp
uv run e2e.py --llm-provider ccs --ccs-profile one

# Bỏ qua scan, dùng lại sessions đã có
uv run e2e.py --sessions-dir data/sessions_2026-06-15_runAt_20260615-103000
```

## Session log ở đâu?

Script tự detect theo OS:

| OS      | Đường dẫn tự tìm |
|---------|-----------------|
| Windows | `~/AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude/local-agent-mode-sessions` |
| macOS   | `~/Library/Application Support/Claude/local-agent-mode-sessions` |
| Linux   | `~/.config/Claude/local-agent-mode-sessions` |

Nếu log ở chỗ khác, set biến môi trường:

```bash
CLAUDE_LOG_ROOT=/path/to/sessions uv run e2e.py
```

## Quét ngày khác

Mở `scripts/scan.py`, đổi `TARGET_DATE` ở đầu file:

| Giá trị | Ý nghĩa |
|---------|---------|
| `""` (bỏ trống) | Hôm nay |
| `"ALL"` | Tất cả session |
| `"2026-06-15"` | Đúng 1 ngày |
| `"2026-06-14, 2026-06-15"` | Nhiều ngày |

## Chạy từng bước thủ công

```bash
uv sync

# 1. Scan
uv run python scripts/scan.py

# 2. Judge
uv run python scripts/judge.py \
    --sessions-dir data/sessions_<label>_runAt_<ts> \
    --top-candidates 5 --min-recurrence 2 --max-deepdive 5

# 3. Synth
uv run python scripts/synth.py \
    --candidates data/judge_<date>/candidate_skills.json \
    --top 3 --timeout 300

# 4. Accept
python data/skills_<date>_proposal/accept.py
```

## Tests

```bash
uv run pytest
```

## Tài liệu

- PRD: `docs/products/PRD.md`
- Design spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`
- Schema field: `docs/agent_responce/data_goal.md`
- Agent debate: `docs/products/agent-debate.md`
