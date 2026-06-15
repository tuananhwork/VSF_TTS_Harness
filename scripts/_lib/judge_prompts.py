"""Prompt strings for Pattern's Lượt 2 judge call.

Kept in one place so the prompt is reviewable as a diff without code noise.
"""

from __future__ import annotations

import json
from typing import Any


JUDGE_SYSTEM = """Bạn là judge phân tích pattern hành vi user trên Claude Cowork.
Focus 2 hành vi: PROCESS_ORCHESTRATION + INEFFICIENT_RETRY.
Tham chiếu schema 7 lớp ở docs/agent_responce/data_goal.md."""


TRIAGE_INSTRUCTIONS = """PASS 1 — TRIAGE (rẻ, chạy trên summary nhiều session).

INPUT là các "group" session gom thô theo tool usage (có thể là 1 session đơn
lẻ). Mỗi group có:
- `intent_seeds`: câu yêu cầu gốc của user từng session — TÍN HIỆU CHÍNH để nhận
  diện task lặp lại, vì `titles` do Claude tự sinh nên khác nhau dù cùng 1 loại
  yêu cầu.
- `tool_sequence_per_session`: chuỗi tool CÓ THỨ TỰ của mỗi session (ví dụ
  ["Read","Edit×2","Bash"]). Dùng để nhận diện flow giống nhau.
- `retry_rate` / `correction_rate` / `behavior_class_hint`: dấu hiệu session có
  nhiều lần sửa/làm lại hay không.

NHIỆM VỤ: tìm các task/flow LẶP LẠI xuyên TẤT CẢ session (merge session từ nhiều
group nếu intent_seeds + tool_sequence giống nhau về ý nghĩa). Với mỗi pattern:
1. Đặt `name` (snake_case, <= 30 ký tự, không trùng installed_skills).
2. Gắn `skill_type`:
   - `process_macro`: flow tốt, lặp lại, đáng đóng gói để gọi lại nhanh.
   - `improvement_lesson`: nhóm có nhiều retry/correction (retry_rate cao hoặc
     behavior_class_hint = "inefficient"). ĐÂY LÀ TÍN HIỆU ĐỂ HỌC — KHÔNG loại bỏ.
3. `behavior_class` ∈ {process, inefficient, not_a_pattern}.
4. `trigger_intent` song ngữ Việt-Anh (khi nào dùng skill này).
5. `evidence.session_ids` + `evidence.source_files` (BẮT BUỘC chính xác — pass 2
   sẽ load trace từ source_files này).
6. `prelim_score`: recurrence / cohesion / personalization (1-5).

CRITIQUE NHẸ (chỉ ở mức này, KHÔNG chấm điểm gắt, KHÔNG tự loại theo recurrence):
- Trùng tên/intent với installed_skills => rejected_reason = "duplicate".
- Pattern quá generic ("file_edit", "ask_question") => "too_generic".
- Không phải pattern thật => "not_a_pattern".

Candidate bị loại VẪN có trong output với rejected_reason set.

Output STRICT JSON array; schema mỗi phần tử:
{
  "name": "...",
  "skill_type": "process_macro" | "improvement_lesson",
  "behavior_class": "process" | "inefficient" | "not_a_pattern",
  "trigger_intent": {"vi": "...", "en": "..."},
  "evidence": {"session_ids": [...], "source_files": [...]},
  "prelim_score": {"recurrence": 1-5, "cohesion": 1-5, "personalization": 1-5},
  "rejected_reason": null | "duplicate" | "too_generic" | "not_a_pattern"
}
KHÔNG kèm prose ngoài JSON."""


DEEPDIVE_INSTRUCTIONS = """PASS 2 — DEEP-DIVE (1 candidate, chạy trên FULL TRACE).

Bạn được cho 1 candidate đã qua triage + recurrence guard, kèm `traces`: trace
CÓ THỨ TỰ của từng evidence session (mỗi bước là user request, chuỗi tool, hoặc
chỗ user `correction`/Claude `retry`).

NHIỆM VỤ — đọc kỹ trace rồi:
1. `action_template`: trích flow CHUẨN theo ĐÚNG THỨ TỰ (bước 1→2→3→4), bám
   `tools` trong trace. KHÔNG đảo thứ tự. Mỗi bước: {"step", "tool", "input_shape"}.
2. `good_points`: cách làm tốt rút ra từ trace (1-4 ý).
3. `weak_points`: điểm chưa tốt — chỗ nào user phải sửa/làm lại là BẰNG CHỨNG cụ
   thể (trích dẫn). Với skill_type = improvement_lesson, đây là phần trọng tâm.
4. `improvement_notes`: lần sau nên làm gì để TỐT HƠN (cụ thể, bám bằng chứng —
   không khuyên chung chung). BẮT BUỘC non-empty nếu skill_type = improvement_lesson.
5. `golden_tests`: 3 cặp {query, expected} dựng từ evidence.
6. `risk_flags` ⊆ {write_action, deletes_files, external_api, sends_message}.
7. `final_score`: recurrence / cohesion / personalization (1-5).
8. Tự critique: nếu sau khi xem trace thấy KHÔNG phải pattern thật, set
   `rejected_reason` = "not_a_pattern" hoặc "low_score".

Output STRICT JSON object (1 candidate đã làm giàu), thêm các field trên vào
candidate. KHÔNG kèm prose ngoài JSON."""


def build_triage_prompt(
    groups: list[dict[str, Any]],
    installed_skills: list[str],
) -> str:
    payload = {"groups": groups, "installed_skills": installed_skills}
    return (
        f"{JUDGE_SYSTEM}\n\n{TRIAGE_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_deepdive_prompt(
    candidate: dict[str, Any],
    traces: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {"candidate": candidate, "traces": traces}
    return (
        f"{JUDGE_SYSTEM}\n\n{DEEPDIVE_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
