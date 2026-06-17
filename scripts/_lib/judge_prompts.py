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
- `repeat_rate` / `failure_rate` / `behavior_class_hint`: tín hiệu CẤU TRÚC —
  `repeat_rate` = tỉ lệ rework (chạy lại tool VỪA FAIL); `failure_rate` = tỉ lệ
  action lỗi (result_ok=False). Cao = session nhiều ma sát.
- `outputs_per_session`: tên file kết quả mỗi session (vd `*.md`, `*.xlsx`,
  `*.pptx`) — loại artifact lặp lại là TÍN HIỆU MẠNH để nhận diện cùng loại task.
- `focused_apps_per_session`: app/cửa sổ user đang thao tác — tín hiệu domain.

NHIỆM VỤ: tìm các task/flow LẶP LẠI xuyên TẤT CẢ session (merge session từ nhiều
group nếu intent_seeds + tool_sequence giống nhau về ý nghĩa). Với mỗi pattern:
1. Đặt `name` (kebab-case theo chuẩn Agent Skills: chỉ a-z, 0-9 và dấu '-',
   KHÔNG dùng '_', không bắt đầu/kết thúc bằng '-', <= 64 ký tự, không trùng
   installed_skills).
2. Gắn `skill_type`:
   - `process_macro`: flow tốt, lặp lại, đáng đóng gói để gọi lại nhanh.
   - `improvement_lesson`: nhóm nhiều ma sát (repeat_rate / failure_rate cao hoặc
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


# ── PASS 2 (debate) is three sub-steps: EXTRACT → JUDGES → CONSOLIDATE.
#    See docs/products/agent-debate.md "Quyết định kiến trúc — Cách B".

EXTRACT_INSTRUCTIONS = """PASS 2 · EXTRACT (1 candidate, chạy trên FULL TRACE).

Bước này TRUNG LẬP: chỉ trích sự thật từ trace, KHÔNG chấm điểm, KHÔNG quyết định
đóng gói hay không (việc đó dành cho các judge + consolidator ở bước sau).

Bạn được cho 1 candidate đã qua triage + recurrence guard, kèm `traces`: trace
CÓ THỨ TỰ của từng evidence session (mỗi bước là user request, chuỗi tool, hoặc
chỗ Claude `repeat` = chạy lại tool vừa fail (rework)).

NHIỆM VỤ — đọc kỹ trace rồi trích:
1. `action_template`: flow CHUẨN theo ĐÚNG THỨ TỰ (bước 1→2→3→4), bám `tools`
   trong trace. KHÔNG đảo thứ tự. Mỗi bước: {"step", "tool", "input_shape"}.
2. `good_points`: cách làm tốt rút ra từ trace (1-4 ý).
3. `weak_points`: điểm chưa tốt — chỗ nào user phải sửa/làm lại là BẰNG CHỨNG cụ
   thể (trích dẫn). Với skill_type = improvement_lesson, đây là phần trọng tâm.
4. `improvement_notes`: lần sau nên làm gì để TỐT HƠN (cụ thể, bám bằng chứng —
   không khuyên chung chung). BẮT BUỘC non-empty nếu skill_type = improvement_lesson.
5. `golden_tests`: 3 cặp {query, expected} dựng từ evidence.
6. `risk_flags` ⊆ {write_action, deletes_files, external_api, sends_message}.

Output STRICT JSON object đúng 6 field trên. KHÔNG kèm prose ngoài JSON."""


# Each judge argues ONE value axis. MVP runs efficiency + quality (cùng phe —
# xem đánh đổi đã ghi trong agent-debate.md). cost/business để pending: thêm vào
# JUDGES khi bật là đủ, không phải sửa orchestration.
_EFFICIENCY_JUDGE = """Bạn là JUDGE NĂNG SUẤT (Efficiency).
Mối quan tâm DUY NHẤT: đóng gói skill này tiết kiệm được bao nhiêu thao tác thủ
công / lượt chat lặp lại? Chuỗi càng dài, càng lặp, càng nhiều bước thủ công →
axis_score càng cao. Một-lần hoặc đã gọn rồi → điểm thấp."""

_QUALITY_JUDGE = """Bạn là JUDGE CHẤT LƯỢNG (Quality).
Mối quan tâm DUY NHẤT: user có phải liên tục sửa sai / đính chính ý định không?
Càng nhiều rework/failure vì prompt thiếu ngữ cảnh hay Input/Output không chuẩn
→ càng cần một skill cố định khung → axis_score càng cao. Flow trơn tru, không
phải sửa → điểm thấp."""

# Pending judges — không nằm trong JUDGES ở MVP. Bật = thêm dict tương ứng vào list.
_COST_JUDGE = """Bạn là JUDGE CHI PHÍ (Cost).
Mối quan tâm DUY NHẤT: pattern có nhồi file thô / dùng model đắt cho việc dễ gây
lãng phí token không? Nếu đóng gói, có nên đẩy phần xử lý thô sang code thay vì
LLM? Đây là vai PHẢN BIỆN — sẵn sàng cho stance="reject" nếu không đáng token."""

_BUSINESS_JUDGE = """Bạn là JUDGE NGHIỆP VỤ (Business).
Mối quan tâm DUY NHẤT: đây có phải luồng làm việc cốt lõi, lặp lại của công ty
hay chỉ là chat tự học cá nhân? Chỉ luồng có giá trị nghiệp vụ mới đáng đóng gói."""


JUDGE_TASK = """NHIỆM VỤ: đọc candidate + facts (đã trích) + traces, rồi phán xét
THEO ĐÚNG TRỤC GIÁ TRỊ CỦA BẠN (bỏ qua mọi trục khác).

Khi cần số liệu, dùng `candidate.metrics` (recurrence/repeat_rate/failure_rate —
tính trên evidence đã merge) làm số thật.

Output STRICT JSON object:
{
  "stance": "approve" | "reject" | "neutral",
  "axis_score": 1-5,      // điểm trên trục của riêng bạn
  "argument": "..."        // 1-3 câu, bám bằng chứng cụ thể trong trace
}
KHÔNG kèm prose ngoài JSON."""


JUDGES: list[dict[str, str]] = [
    {"id": "efficiency", "label_vi": "Năng suất", "label_en": "Efficiency",
     "persona": _EFFICIENCY_JUDGE},
    {"id": "quality", "label_vi": "Chất lượng", "label_en": "Quality",
     "persona": _QUALITY_JUDGE},
]


CONSOLIDATOR_INSTRUCTIONS = """PASS 2 · CONSOLIDATOR (chốt 1 candidate).

Bạn nhận candidate, facts đã trích, và `verdicts` — phán xét của từng judge theo
trục riêng (mỗi verdict có stance / axis_score / argument; verdict có `error` là
judge lỗi, cứ coi như khuyết). Tổng hợp lại thành quyết nghị cuối:

LƯU Ý SỐ THẬT: `candidate.metrics` (recurrence / repeat_rate / failure_rate) được
TÍNH LẠI bằng code trên đúng tập evidence đã merge — ĐÂY là số thật để chấm axis
recurrence; bỏ qua mọi behavior_class_hint per-group cũ nếu mâu thuẫn.

1. `final_score`: recurrence / cohesion / personalization (1-5) — quy các
   axis_score + lập luận của judge về 3 trục chuẩn này.
2. `rejected_reason`: null nếu DUYỆT; "low_score" nếu các judge đều chấm thấp /
   không đáng đóng gói; "not_a_pattern" nếu thực ra không phải pattern thật.
   BẠN ĐƯỢC PHÉP BÁC dù judge đồng thuận — đừng làm con dấu cao su.
3. `consolidator_note`: 1-2 câu lý do quyết nghị, có nhắc tới điểm bất đồng (nếu có).

Output STRICT JSON object đúng 3 field trên. KHÔNG kèm prose ngoài JSON."""


def build_triage_prompt(
    groups: list[dict[str, Any]],
    installed_skills: list[str],
) -> str:
    payload = {"groups": groups, "installed_skills": installed_skills}
    return (
        f"{JUDGE_SYSTEM}\n\n{TRIAGE_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_extract_prompt(
    candidate: dict[str, Any],
    traces: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {"candidate": candidate, "traces": traces}
    return (
        f"{JUDGE_SYSTEM}\n\n{EXTRACT_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_judge_prompt(
    judge: dict[str, str],
    candidate: dict[str, Any],
    facts: dict[str, Any],
    traces: dict[str, list[dict[str, Any]]],
) -> str:
    payload = {"candidate": candidate, "facts": facts, "traces": traces}
    header = f"[{judge['label_vi']} / {judge['label_en']}]"
    return (
        f"{header}\n{judge['persona']}\n\n{JUDGE_TASK}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_consolidator_prompt(
    candidate: dict[str, Any],
    facts: dict[str, Any],
    verdicts: list[dict[str, Any]],
) -> str:
    payload = {"candidate": candidate, "facts": facts, "verdicts": verdicts}
    return (
        f"{JUDGE_SYSTEM}\n\n{CONSOLIDATOR_INSTRUCTIONS}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
