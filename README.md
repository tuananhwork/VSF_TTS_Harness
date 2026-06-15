# Pattern — Behavior → Skill harness for Claude Cowork (MVP)

Quan sát hành vi user trên Claude Cowork → đề xuất Skill draft cá nhân hoá.
Spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`.

## Yêu cầu

- Python 3.12+, `uv`
- Claude Code CLI có sẵn trên `PATH` (`claude` binary)
- Đã có session log Claude Cowork trên máy

## Cài đặt

```bash
uv sync
```

## Pipeline 3 bước

### 1) Scan — trích session JSONL từ log Claude Desktop

```bash
uv run python scripts/scan.py
```

Mặc định scan ngày hôm nay; xem `TARGET_DATE` trong `scripts/scan.py` để đổi.
Output: `data/sessions_<date>_runAt_<runTs>/`.

### 2) Judge — cluster + LLM-as-judge → candidate skills

```bash
uv run python scripts/judge.py \
    --sessions-dir data/sessions_<date>_runAt_<runTs> \
    --min-size 2 --top-candidates 5
```

Output: `data/judge_<date>/{cluster_summary.json, pattern_report.md, candidate_skills.json}`.

### 3) Synth — sinh skill draft + proposal

```bash
uv run python scripts/synth.py \
    --candidates data/judge_<date>/candidate_skills.json \
    --top 3 --timeout 120
```

Output: `data/skills_<date>_proposal/{PROPOSAL.md, accept.py, <skill-name>/...}`.

### 4) Accept — cài skill bạn duyệt

```bash
python data/skills_<date>_proposal/accept.py
```

Hoặc non-interactive: `python ... accept.py 1 3`.

## Tests

```bash
uv run pytest
```

## Tài liệu

- PRD: `docs/products/PRD.md`
- Schema 7 lớp field: `docs/agent_responce/data_goal.md`
- Lượt 1 implementation notes: `docs/agent_responce/session_notes.md`
- Design spec: `docs/superpowers/specs/2026-06-13-pattern-end-to-end-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-13-pattern-end-to-end-pipeline.md`
