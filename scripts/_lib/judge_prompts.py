"""Prompt strings for Pattern's Lượt 2 judge call.

Kept in one place so the prompt is reviewable as a diff without code noise.
"""

from __future__ import annotations

import json
from typing import Any


JUDGE_SYSTEM = """Bạn là judge phân tích pattern hành vi user trên Claude Cowork.
Focus 2 hành vi: PROCESS_ORCHESTRATION + INEFFICIENT_RETRY.
Tham chiếu schema 7 lớp ở docs/agent_responce/data_goal.md."""


JUDGE_INSTRUCTIONS = """INPUT là các "group" session được gom sơ bộ theo tool
usage (có thể là 1 session đơn lẻ). Field `intent_seeds` chứa câu yêu cầu gốc
của user cho mỗi session — đây là tín hiệu chính để nhận diện pattern, vì
`titles` do Claude tự sinh dựa trên nội dung file/chủ đề nên có thể khác nhau
dù cùng 1 loại yêu cầu (ví dụ "Tóm tắt file", "đọc và tóm tắt file sau",
"tóm tắt" đều là cùng pattern "tóm tắt file user upload").

Nhiệm vụ: tự tìm các pattern hành vi LẶP LẠI xuyên suốt TẤT CẢ session trong
INPUT (có thể merge session từ nhiều group khác nhau nếu intent_seeds giống
nhau về ý nghĩa, dù khác group/khác title). Với mỗi pattern tìm được:
1. Xác định behavior_class ∈ {process, inefficient, not_a_pattern}
2. Đặt tên pattern (snake_case, <= 30 ký tự, không trùng installed_skills)
3. Mô tả trigger_intent song ngữ Việt-Anh (khi nào dùng skill này)
4. Trích action_template (chuỗi tool + input shape ngắn gọn)
5. Score: recurrence (1-5), cohesion (1-5), personalization (1-5)
6. Risk flags từ tập: write_action, deletes_files, external_api, sends_message

CRITIQUE INLINE (tự đóng cả vai critique trước khi output):
- Trùng tên hoặc trùng intent với installed_skills => loại
- Tổng score < 9 => loại
- Pattern chỉ xuất hiện ở 1 session (không có >=2 session cùng intent) => loại
- Pattern quá generic (ví dụ "file_edit", "ask_question") => loại

Mỗi candidate bị loại vẫn có trong output với rejected_reason set; những pattern
là not_a_pattern thì rejected_reason = "not_a_pattern".

Output STRICT JSON array; schema mỗi phần tử:
{
  "name": "...",
  "trigger_intent": {"vi": "...", "en": "..."},
  "action_template": [{"tool": "...", "input_shape": "..."}],
  "evidence": {"session_ids": [...], "process_names": [...]},
  "score": {"recurrence": 1-5, "cohesion": 1-5, "personalization": 1-5},
  "behavior_class": "process" | "inefficient" | "not_a_pattern",
  "risk_flags": [...],
  "rejected_reason": null | "duplicate" | "low_score" | "low_recurrence" | "too_generic" | "not_a_pattern"
}
KHÔNG kèm prose ngoài JSON."""


def build_judge_prompt(
    clusters: list[dict[str, Any]],
    installed_skills: list[str],
) -> str:
    payload = {
        "groups": clusters,
        "installed_skills": installed_skills,
    }
    return (
        f"{JUDGE_SYSTEM}\n\n{JUDGE_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
