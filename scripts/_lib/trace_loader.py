"""Load full ordered per-turn traces for the Lượt 2 deep-dive stage.

Where aggregator.py works on count-aggregated summaries (cheap triage), the
deep-dive needs to *see the flow*: the user request, the ordered tool calls,
and exactly where the user corrected or Claude retried. That signal lives in
the `turn` records scan.py writes; this module reconstructs a compact,
ordered view of them.

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


def _step(turn: dict, max_text: int) -> dict:
    role = turn.get("role")
    feedback = turn.get("feedback_flag")
    if role == "user":
        text = turn.get("user_text") or ""
        return {"role": "user", "text": _truncate(text, max_text), "feedback": feedback}
    tools = _compress_runs(
        [a.get("tool_name", "") for a in (turn.get("actions") or [])]
    )
    return {"role": "assistant", "tools": tools, "feedback": feedback}


def load_trace(path: Path, *, max_turns: int = 40, max_text: int = 300) -> list[dict]:
    """Reconstruct an ordered, compact trace from one session JSONL.

    Reads `turn` records in file order. When a session exceeds `max_turns`,
    keeps the head and tail (corrections usually surface near the end) so the
    deep-dive still sees both the setup and the friction.
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
                steps.append(_step(rec, max_text))

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
    max_text: int = 300,
) -> dict[str, list[dict]]:
    """Load traces for the given session files, keyed by session_id."""
    traces: dict[str, list[dict]] = {}
    for fname in source_files:
        path = sessions_dir / fname
        if not path.exists():
            continue
        sid = _read_session_id(path)
        traces[sid] = load_trace(path, max_turns=max_turns, max_text=max_text)
    return traces
