# Synth (Lượt 3) — Skill-format overhaul

Date: 2026-06-16
Status: Approved (design)
Supersedes the skill-generation half of `scripts/synth.py` + `_lib/render_proposal.py::render_skill_dir`.

## Problem

Step 3 (`synth.py`) sinh skill draft "khá đần", chưa đúng chuẩn Agent Skills và
vi phạm các nguyên tắc mentor đặt ra:

- **Multilingual bloat** — mỗi mục lặp song song VI + EN, SKILL.md phình to.
- **Evidence nhúng trong skill** — có `## Evidence`, "Skill được rút từ session…",
  `generated_by` / `generated_on` trong frontmatter. Đây là *lịch sử ra đời* của
  skill — thứ skill **không** được chứa.
- **Không tách năng lực** — skill nhiều bước vẫn nhồi vào một SKILL.md, không có
  `references/` cho từng năng lực (mentor: "git skill có push/pull/merge thì mỗi
  cái là 1 ref").
- **Hai path sinh không đồng đều** — Path A (skill-creator headless, output tự do)
  khó ép đúng format; Path B template thì cứng.

Mentor's rubric (nguồn yêu cầu):
- Skill chỉ là **chỉ dẫn**: trả lời *KHI NÀO dùng* (trigger trong description),
  *năng lực gì*, mỗi năng lực *làm những bước nào*.
- Quá nhiều năng lực → tách `SKILL.md` (index) + `references/` (chi tiết từng năng lực).
- **Deterministic được thì đẩy qua code**; thứ **cần reasoning** (vd diễn giải bài
  học, đo hiệu quả) thì **không** dùng script.
- Evidence **tách khỏi skill**: `<skill_code>/<hash+time>/evidence.md` cho mỗi change.
- Skill **không** trả lời: lịch sử ra đời, plan/spec tạo ra nó, phạm vi hệ thống.

## Decisions (chốt)

| Quyết định | Chọn |
| --- | --- |
| Ngôn ngữ skill | **English toàn bộ** (đúng convention, trigger match tốt) |
| Evidence | **Subfolder đi cùng skill**: `<skill>/evidence/<time>_<hash>/evidence.md`; accept.py copy cả evidence |
| Cơ chế sinh | **Template deterministic là chính** — bỏ Path A; LLM chỉ lo phần cần reasoning |
| Tách references | **Theo ngưỡng**: LLM trả `capabilities`; `>1` → tách `references/`; guardrail cap 6 ref |
| `related` skills | Chỉ trong cùng batch synth (chưa có global skill index) |
| Forced split theo step-count | Không — không cắt giữa một capability; chỉ tách theo số capability |

## Architecture — một call reasoning, rồi assembly deterministic

Mỗi accepted candidate đi qua 2 stage:

### Stage 1 — `render_skill(candidate)` (LLM call duy nhất, `run_claude_json`)

Input: candidate JSON (đa phần tiếng Việt). Output: **strict JSON tiếng Anh**, chỉ
chứa thứ **cần reasoning**:

```json
{
  "description": "<when-to-use + trigger, English, <=1024 chars>",
  "overview": "<1-2 câu nêu các năng lực>",
  "capabilities": [
    {
      "slug": "run-tests",
      "title": "Run the project test suite",
      "when": "<khi nào dùng năng lực này>",
      "steps": ["<bước 1>", "<bước 2>"],
      "deterministic_script": {            // optional
        "name": "run_tests.sh",
        "purpose": "<mô tả>",
        "command": "<lệnh dự kiến>"
      }
    }
  ],
  "red_flags": ["<dấu hiệu đang lặp lỗi cũ / sắp side-effect>"],
  "core_lesson": "<chỉ improvement_lesson: bài học cốt lõi>",
  "golden_tests": [
    {"query": "<English>", "expected": "<English>"}
  ],
  "related": ["<slug skill khác cùng batch>"]
}
```

LLM chịu trách nhiệm: dịch sang English, **decompose năng lực**, viết prose chỉ dẫn,
red flags, golden tests, và **quyết định bước nào deterministic** (gắn
`deterministic_script`). Một call cho mỗi candidate.

### Stage 2 — assembler Python (KHÔNG LLM)

Dựng folder từ `render_skill` output + raw candidate:

- `len(capabilities) <= 1` → **một SKILL.md**, flow inline trong `## Capability`.
- `len(capabilities) > 1` (cap tối đa 6) → **SKILL.md là index** (overview + bảng
  capability) + `references/<slug>.md` cho từng capability.
- Mỗi capability có `deterministic_script` → ghi **stub trung thực** vào
  `scripts/<name>`: header comment + lệnh dự kiến + `TODO`. **Không bịa logic chạy
  được**; stub nói rõ nó là stub.
- `evidence/<YYYYMMDD-HHMM>_<hash8>/evidence.md` — toàn bộ provenance (xem dưới).
- `golden_tests.md` (English) — giữ để chạy tay.

### SKILL.md shape (English, chỉ chỉ dẫn)

```
---
name: <slug>
description: <when-to-use + trigger, English, <=1024>
metadata:
  skill_type: process_macro | improvement_lesson
  risk_flags: [write_action, sends_message]
---

# <slug>

## When to use
<from description, mở rộng 1-2 dòng>

## Capabilities
<nếu 1 capability: flow inline (numbered steps)>
<nếu nhiều: bảng | Capability | When | Detail | → references/<slug>.md>

## Red flags
- <STOP signals>

## Related skills          # chỉ khi related không rỗng
- `<other-slug>`
```

improvement_lesson: thêm `## Core lesson` (từ `core_lesson`) đặt trước Capabilities;
flow là context hỗ trợ.

**Loại khỏi SKILL.md:** `generated_by`, `generated_on`, `## Evidence`, "rút từ
session…", risk-flag dạng kể-lể evidence. Risk flag chỉ còn ở `metadata.risk_flags`
+ bước confirm mà nó kích hoạt trong flow.

### Evidence folder (đi cùng skill)

`<skill>/evidence/<YYYYMMDD-HHMM>_<hash8>/evidence.md`:

- `hash8` = hash 8 ký tự của **nội dung SKILL.md** đã dựng. Mỗi lần regenerate mà
  nội dung **đổi** → thư mục mới theo thời gian (lịch sử change). Hash trùng → skip
  ghi evidence mới (idempotent).
- `evidence.md` chứa: `session_ids`, `source_files`, good/weak/improvement points
  **bản gốc (VI)** như raw evidence, debate verdicts, metrics (recurrence/repeat/
  failure_rate), nguồn golden test. Đây là nơi duy nhất chứa "lịch sử ra đời".

`accept.py` copy nguyên folder skill **bao gồm** `evidence/`.

## Phân vai deterministic vs reasoning (theo mentor)

- **Code (deterministic):** layout folder/file, dựng frontmatter, slug name, scaffold
  `references/`, tạo evidence dir + content hash, và **quality-gate validator**.
- **LLM (reasoning):** render English, decompose capability, viết prose chỉ dẫn,
  red flags, golden tests, chọn bước deterministic.

### Quality gate — `validate_skill(skill_dir)` (code, no LLM)

Chạy sau khi dựng mỗi skill. Fail → ghi cờ trong PROPOSAL.md, không chặn cả run.
Checks:

1. Frontmatter có **đúng** 3 key top-level: `name`, `description`, `metadata`
   (không thừa key nào ở top-level).
2. `name` == tên folder; khớp regex slug (`^[a-z0-9]+(-[a-z0-9]+)*$`, ≤64).
3. `description` non-empty, ≤1024 ký tự.
4. SKILL.md **không** chứa section "Evidence", chuỗi "generated_on/generated_by",
   hay "rút từ session" (chống leak birth-history).
5. Mọi `references/<slug>.md` được link trong index đều tồn tại, và ngược lại
   không có ref mồ côi.

## Bỏ / Hoãn

- **Bỏ:** Path A (skill-creator headless). Assembler thành path duy nhất.
- **Hoãn (ghi rõ, ngoài scope lần này):** khuyến nghị model-routing/sub-agent *bên
  trong* skill sinh ra; Claude Code hook làm gate (validator Python đã phủ nhu cầu
  gate lúc này); global skill index cho `related`.

## Components & files

| File | Thay đổi |
| --- | --- |
| `scripts/synth.py` | Bỏ Path A/B; gọi `render_skill` (Stage 1) → `assemble_skill` (Stage 2) → `validate_skill`. Giữ phần đọc candidates, top-N, emit accept.py, PROPOSAL.md. |
| `scripts/_lib/skill_render.py` (mới) | Prompt + schema cho `render_skill` (Stage 1, LLM). |
| `scripts/_lib/skill_assemble.py` (mới) | `assemble_skill`, `write_evidence`, single-vs-split, scripts stub — deterministic. |
| `scripts/_lib/skill_validate.py` (mới) | `validate_skill` quality gate. |
| `scripts/_lib/synth_templates/` | Template English mới: `SKILL.md.j2` (index + inline), `reference.md.j2`, `evidence.md.j2`, `golden_tests.md.j2`, `script_stub.j2`. |
| `scripts/_lib/render_proposal.py` | Bỏ `render_skill_dir` (thay bằng assembler); giữ `build_skill_description` (tái dùng), `render_pattern_report`. |
| `data/.../accept.py` (emit) | Đảm bảo copy cả `evidence/`. |

## Testing

Assembler + validator deterministic → unit test trực tiếp, mock Stage-1 LLM:

- `test_skill_assemble.py`: single-capability → 1 SKILL.md no refs; multi → index +
  đúng số `references/`; cap 6; evidence dir tên `<time>_<hash8>` + nội dung; script
  stub khi có `deterministic_script`; idempotent theo hash.
- `test_skill_validate.py`: pass case sạch; fail khi thừa frontmatter key, name≠folder,
  description rỗng/>1024, leak "Evidence"/"generated_on", ref mồ côi/thiếu.
- Cập nhật/loại `test_render_proposal.py` phần `render_skill_dir`.

## Acceptance

1. SKILL.md sinh ra **English-only**, frontmatter đúng 3 key, không chứa
   evidence/birth-history.
2. Skill nhiều capability có `references/<slug>.md`; skill một capability giữ 1 file.
3. Evidence nằm ở `<skill>/evidence/<time>_<hash>/evidence.md`, không trong SKILL.md;
   accept.py copy theo.
4. Bước deterministic có `scripts/` stub trung thực (không bịa logic).
5. `validate_skill` chạy mọi skill; PROPOSAL.md cờ skill fail gate.
6. `uv run pytest` xanh.
