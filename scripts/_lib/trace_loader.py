"""Load full ordered per-turn traces for the Lượt 2 deep-dive stage.

Where aggregator.py works on count-aggregated summaries (cheap triage), the
deep-dive needs to *see the flow*: the user request, the ordered tool calls,
and exactly where Claude reworked a failed tool (the `repeat` flag). That
signal lives in the `turn` records scan.py writes; this module reconstructs a
compact, ordered view of them.

Pure Python. No LLM.
"""

from __future__ import annotations

import json
from pathlib import Path


def _compress_runs(seq: list[str]) -> list[str]:
    """Collapse consecutive duplicate tool names: [A,A,B] -> [A×2, B]."""
    out: list[str] = []
    for name in seq:
        if out and out[-1].split("×")[0] == name:
            prev = out[-1].split("×")
            k = int(prev[1]) + 1 if len(prev) == 2 else 2
            out[-1] = f"{name}×{k}"
        else:
            out.append(name)
    return out


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _compact_input(inp, limit: int) -> str | None:
    """Compact, length-capped view of an action's input_summary.

    The deep-dive's EXTRACT step needs the tool's input *shape* (and often the
    actual args/content) to write `action_template` + cite weak points; scan
    already trimmed nested strings, so we just flatten to JSON and cap length.
    """
    if inp is None:
        return None
    s = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False, default=str)
    return _truncate(s, limit) if s else None


def _step(turn: dict, max_text: int, max_input: int) -> dict:
    role = turn.get("role")
    feedback = turn.get("feedback_flag")
    if role == "user":
        text = turn.get("user_text") or ""
        return {"role": "user", "text": _truncate(text, max_text), "feedback": feedback}

    actions = turn.get("actions") or []
    tools = _compress_runs([a.get("tool_name", "") for a in actions])
    step: dict = {"role": "assistant", "tools": tools, "feedback": feedback}

    # What Claude actually said/produced this turn — evidence for good/weak points.
    text = turn.get("text_summary")
    if text:
        step["text"] = _truncate(text, max_text)

    # Per-action detail: input shape + failure outcome. Only emitted when it
    # carries signal (has input, or the action FAILED) so clean turns stay light.
    details: list[dict] = []
    for a in actions:
        d: dict = {"tool": a.get("tool_name", "")}
        ci = _compact_input(a.get("input_summary"), max_input)
        if ci:
            d["input"] = ci
        if a.get("result_ok") is False:
            d["ok"] = False
            err = a.get("error_kind")
            if err:
                d["error"] = _truncate(str(err), max_input)
        if len(d) > 1:  # more than just the tool name → worth including
            details.append(d)
    if details:
        step["actions"] = details
    return step


def load_trace(
    path: Path, *, max_turns: int = 40, max_text: int = 600, max_input: int = 300,
) -> list[dict]:
    """Reconstruct an ordered, compact trace from one session JSONL.

    Reads `turn` records in file order. Each step keeps the user/assistant text,
    the ordered tool sequence, and — for assistant turns — per-action input shape
    and failure outcomes (so EXTRACT can derive `action_template`/`input_shape`
    and cite friction). When a session exceeds `max_turns`, keeps the head and
    tail (corrections usually surface near the end) so the deep-dive still sees
    both the setup and the friction.
    """
    steps: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("record_type") == "turn":
                steps.append(_step(rec, max_text, max_input))

    if len(steps) > max_turns:
        head = max_turns // 2
        tail = max_turns - head
        steps = steps[:head] + [{"role": "elided", "skipped": len(steps) - max_turns}] + steps[-tail:]
    return steps


def _read_session_id(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("record_type") == "session_summary":
                return rec.get("session_id") or path.stem
    return path.stem


def load_traces(
    source_files: list[str], sessions_dir: Path, *, max_turns: int = 40,
    max_text: int = 600, max_input: int = 300,
) -> dict[str, list[dict]]:
    """Load traces for the given session files, keyed by session_id."""
    traces: dict[str, list[dict]] = {}
    for fname in source_files:
        path = sessions_dir / fname
        if not path.exists():
            continue
        sid = _read_session_id(path)
        traces[sid] = load_trace(
            path, max_turns=max_turns, max_text=max_text, max_input=max_input,
        )
    return traces
