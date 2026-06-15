"""Scan Claude cowork session logs for a given date and emit per-session JSONL.

Output is designed for an LLM-as-judge that extracts personalized skills from
recurring action patterns. See docs/data_goal.md for the field rationale.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Root folder that contains <userId>/<workspaceId>/local_<sessionId>/audit.jsonl
SOURCE_LOG_ROOT = Path(
    r"C:\Users\chuba\AppData\Local\Packages\Claude_pzs8sxrjxfjjc"
    r"\LocalCache\Roaming\Claude\local-agent-mode-sessions"
)

# SOURCE_LOG_ROOT = Path(r"C:\User\chuba")

# YYYY-MM-DD. Leave None to use today's date.
# A session is included if its [createdAt, lastActivityAt] window touches this date.
TARGET_DATE: str | None = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"

# ── Structural feedback signals ───────────────────────────────────────────────
#
# Feedback is derived from turn/action *structure*, not phrase lists, so it
# holds across languages: `repeat` = same tool re-run in a later turn within
# the window; `pivot` = a user turn that changed the assistant's tool direction.

REPEAT_WINDOW_SECONDS = 60
# Jaccard distance between the assistant toolset before vs. after a user turn,
# above which the user turn is treated as having pivoted the plan.
PIVOT_CHURN_THRESHOLD = 0.5

# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ActionRecord:
    tool_use_id: str | None
    tool_name: str
    mcp_server: str
    input_summary: Any
    result_ok: bool | None = None
    error_kind: str | None = None
    parent_tool_use_id: str | None = None


@dataclass
class TurnRecord:
    idx: int
    ts: str | None
    role: str  # "user" | "assistant"
    user_text: str | None = None
    thinking_summary: str | None = None
    text_summary: str | None = None
    actions: list[ActionRecord] = field(default_factory=list)
    feedback_flag: str | None = None  # "pivot" | "repeat"
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class SessionSummary:
    session_id: str
    title: str | None
    intent_seed: str | None
    model: str | None
    process_name: str | None
    workspace_id: str | None
    user_selected_folders: list[str]
    created_at: str | None
    last_activity_at: str | None
    duration_seconds: float | None
    is_archived: bool | None
    total_turns: int
    total_user_turns: int
    total_assistant_turns: int
    total_actions: int
    total_input_tokens: int
    total_output_tokens: int
    tool_usage: dict[str, int]
    tool_sequence: list[str]
    mcp_usage: dict[str, int]
    pivot_count: int
    repeat_count: int
    rate_limit_hits: int
    outputs_produced: int


# ── Utilities ─────────────────────────────────────────────────────────────────


def parse_target_date() -> date:
    return (
        datetime.strptime(TARGET_DATE, "%Y-%m-%d").date()
        if TARGET_DATE
        else datetime.now().date()
    )


def epoch_ms_to_date(ms: int | None) -> date | None:
    return datetime.fromtimestamp(ms / 1000).date() if ms else None


def iso_to_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def compress_runs(seq: list[str]) -> list[str]:
    """Collapse consecutive duplicate tool names: [A,A,B] -> [A×2, B].

    Preserves order; keeps the flow readable for the LLM judge while marking
    repetition (e.g. a tight repeat loop shows up as `click×6`)."""
    out: list[str] = []
    for name in seq:
        if out and out[-1].split("×")[0] == name:
            prev = out[-1].split("×")
            k = int(prev[1]) + 1 if len(prev) == 2 else 2
            out[-1] = f"{name}×{k}"
        else:
            out.append(name)
    return out


def split_tool_name(name: str) -> tuple[str, str]:
    """mcp__<server>__<method> → (server, method); otherwise (builtin, name)."""
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            return parts[1], parts[2]
    return "builtin", name


def truncate(s: Any, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + f"…[+{len(s) - n}]"


def trim_input(payload: Any, max_str: int = 300) -> Any:
    if isinstance(payload, str):
        return truncate(payload, max_str)
    if isinstance(payload, list):
        return [trim_input(x, max_str) for x in payload[:20]]
    if isinstance(payload, dict):
        return {k: trim_input(v, max_str) for k, v in payload.items()}
    return payload


def extract_user_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return "\n".join(c for c in chunks if c) or None
    return None


# ── Structural feedback signals ───────────────────────────────────────────────


def _assistant_tools(turn: TurnRecord) -> set[str]:
    return {a.tool_name for a in turn.actions}


def mark_pivot_turns(
    turns: list[TurnRecord], threshold: float = PIVOT_CHURN_THRESHOLD
) -> None:
    """Flag user turns that pivoted the assistant's tool direction.

    A user turn is a `pivot` when the toolset the assistant used *after* it
    diverges from the toolset *before* it (Jaccard distance >= threshold). Both
    sides must be non-empty, so an opening instruction (no prior flow) or a
    closing remark (no following actions) never counts. Purely structural — no
    vocabulary, so it is language-agnostic. Mutates `turns` in place."""
    for i, turn in enumerate(turns):
        if turn.role != "user" or turn.feedback_flag is not None:
            continue
        before: set[str] = set()
        for prev in reversed(turns[:i]):
            if prev.role == "user":
                break
            before |= _assistant_tools(prev)
        after: set[str] = set()
        for nxt in turns[i + 1:]:
            if nxt.role == "user":
                break
            after |= _assistant_tools(nxt)
        if not before or not after:
            continue
        distance = 1.0 - len(before & after) / len(before | after)
        if distance >= threshold:
            turn.feedback_flag = "pivot"


# ── Session parsing ───────────────────────────────────────────────────────────


def load_meta(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def session_touches_date(meta: dict[str, Any], target: date) -> bool:
    created = epoch_ms_to_date(meta.get("createdAt"))
    last = epoch_ms_to_date(meta.get("lastActivityAt"))
    start = created or last
    end = last or created
    return bool(start and end and start <= target <= end)


def parse_session(
    meta_path: Path, audit_path: Path, workspace_id: str
) -> tuple[SessionSummary, list[TurnRecord], list[dict[str, Any]]]:
    meta = load_meta(meta_path)
    turns: list[TurnRecord] = []
    rate_limits: list[dict[str, Any]] = []
    tool_usage: dict[str, int] = {}
    tool_sequence: list[str] = []
    mcp_usage: dict[str, int] = {}
    actions_by_tool_use_id: dict[str, ActionRecord] = {}
    last_tool_seen: dict[str, tuple[datetime, int]] = {}
    seen_uuids: set[str] = set()
    turn_idx = 0

    for event in iter_jsonl(audit_path):
        if not isinstance(event, dict):
            continue

        # Dedupe — the audit log emits both `assistant` and `message` envelopes
        # for the same content; uuid is stable across them.
        uid = event.get("uuid")
        if uid and uid in seen_uuids:
            continue
        if uid:
            seen_uuids.add(uid)

        etype = event.get("type")
        ts = event.get("_audit_timestamp") or event.get("timestamp")

        # — Rate-limit signal —
        if etype == "rate_limit_event":
            rl = event.get("rate_limit_info") or {}
            rate_limits.append({
                "ts": ts,
                "status": rl.get("status"),
                "rate_limit_type": rl.get("rateLimitType"),
                "resets_at": rl.get("resetsAt"),
                "overage_status": rl.get("overageStatus"),
            })
            continue

        # — User-envelope events (real user turn OR wrapped tool_result) —
        if etype == "user" and not event.get("isReplay"):
            content = event.get("message", {}).get("content")
            is_tool_result = isinstance(content, list) and any(
                isinstance(c, dict) and c.get("type") == "tool_result" for c in content
            )
            if is_tool_result:
                for c in content:
                    if not isinstance(c, dict) or c.get("type") != "tool_result":
                        continue
                    a = actions_by_tool_use_id.get(c.get("tool_use_id", ""))
                    if not a:
                        continue
                    is_err = c.get("is_error") is True
                    a.result_ok = not is_err
                    if is_err:
                        raw = c.get("content")
                        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                            a.error_kind = truncate(raw[0].get("text", "error"), 200)
                        else:
                            a.error_kind = truncate(raw, 200) if raw else "error"
                continue

            text = extract_user_text(content)
            turn_idx += 1
            turns.append(TurnRecord(
                idx=turn_idx,
                ts=ts,
                role="user",
                user_text=truncate(text, 4000) if text else None,
            ))
            continue

        # — Assistant turn (assistant or message envelope) —
        if etype in ("assistant", "message"):
            msg = event.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            usage = msg.get("usage") or {}
            turn_idx += 1
            t = TurnRecord(
                idx=turn_idx,
                ts=ts,
                role="assistant",
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
            thoughts, texts = [], []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "thinking":
                    thoughts.append(block.get("thinking", ""))
                elif btype == "text":
                    texts.append(block.get("text", ""))
                elif btype == "tool_use":
                    name = block.get("name", "")
                    mcp, _ = split_tool_name(name)
                    tool_usage[name] = tool_usage.get(name, 0) + 1
                    tool_sequence.append(name)
                    mcp_usage[mcp] = mcp_usage.get(mcp, 0) + 1
                    trimmed = trim_input(block.get("input"))
                    # Repeat = the same tool name re-run in a *later* turn within
                    # the window. Cross-turn only: several Edits in one turn is
                    # normal batching, not a redo. Language-free, no input hash.
                    dt = iso_to_dt(ts)
                    prev = last_tool_seen.get(name)
                    if dt and prev:
                        prev_dt, prev_idx = prev
                        if (
                            prev_idx < turn_idx
                            and (dt - prev_dt).total_seconds() <= REPEAT_WINDOW_SECONDS
                            and t.feedback_flag is None
                        ):
                            t.feedback_flag = "repeat"
                    if dt:
                        last_tool_seen[name] = (dt, turn_idx)
                    a = ActionRecord(
                        tool_use_id=block.get("id"),
                        tool_name=name,
                        mcp_server=mcp,
                        input_summary=trimmed,
                        parent_tool_use_id=event.get("parent_tool_use_id"),
                    )
                    t.actions.append(a)
                    if a.tool_use_id:
                        actions_by_tool_use_id[a.tool_use_id] = a
            if thoughts:
                t.thinking_summary = truncate("\n".join(thoughts), 800)
            if texts:
                t.text_summary = truncate("\n".join(texts), 800)
            turns.append(t)
            continue

    # Structural feedback: mark user turns that pivoted the tool direction.
    mark_pivot_turns(turns)

    # Outcome — count produced output files
    outputs_folder = audit_path.parent / "outputs"
    outputs_produced = (
        sum(1 for p in outputs_folder.rglob("*") if p.is_file())
        if outputs_folder.exists() else 0
    )

    duration = None
    if meta.get("createdAt") and meta.get("lastActivityAt"):
        duration = (meta["lastActivityAt"] - meta["createdAt"]) / 1000.0

    summary = SessionSummary(
        session_id=meta.get("sessionId") or meta_path.stem,
        title=meta.get("title"),
        intent_seed=truncate(meta.get("initialMessage") or "", 1000) or None,
        model=meta.get("model"),
        process_name=meta.get("processName"),
        workspace_id=workspace_id,
        user_selected_folders=meta.get("userSelectedFolders") or [],
        created_at=(datetime.fromtimestamp(meta["createdAt"] / 1000).isoformat()
                    if meta.get("createdAt") else None),
        last_activity_at=(datetime.fromtimestamp(meta["lastActivityAt"] / 1000).isoformat()
                          if meta.get("lastActivityAt") else None),
        duration_seconds=duration,
        is_archived=meta.get("isArchived"),
        total_turns=len(turns),
        total_user_turns=sum(1 for t in turns if t.role == "user"),
        total_assistant_turns=sum(1 for t in turns if t.role == "assistant"),
        total_actions=sum(len(t.actions) for t in turns),
        total_input_tokens=sum(t.input_tokens for t in turns),
        total_output_tokens=sum(t.output_tokens for t in turns),
        tool_usage=dict(sorted(tool_usage.items(), key=lambda kv: -kv[1])),
        tool_sequence=compress_runs(tool_sequence),
        mcp_usage=dict(sorted(mcp_usage.items(), key=lambda kv: -kv[1])),
        pivot_count=sum(1 for t in turns if t.feedback_flag == "pivot"),
        repeat_count=sum(1 for t in turns if t.feedback_flag == "repeat"),
        rate_limit_hits=len(rate_limits),
        outputs_produced=outputs_produced,
    )
    return summary, turns, rate_limits


def write_session(
    out_dir: Path,
    summary: SessionSummary,
    turns: list[TurnRecord],
    rate_limits: list[dict[str, Any]],
) -> Path:
    safe_id = summary.session_id.replace("local_", "")[:12]
    fname = f"{summary.process_name or 'session'}__{safe_id}.jsonl"
    out_path = out_dir / fname
    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"record_type": "session_summary", **asdict(summary)}, ensure_ascii=False) + "\n")
        for t in turns:
            f.write(json.dumps({"record_type": "turn", **asdict(t)}, ensure_ascii=False) + "\n")
        for rl in rate_limits:
            f.write(json.dumps({"record_type": "rate_limit", **rl}, ensure_ascii=False) + "\n")
    return out_path


def discover_sessions(root: Path) -> Iterable[tuple[Path, Path, str]]:
    if not root.exists():
        return
    for user_dir in root.iterdir():
        if not user_dir.is_dir() or user_dir.name == "skills-plugin":
            continue
        for ws_dir in user_dir.iterdir():
            if not ws_dir.is_dir():
                continue
            for meta in ws_dir.glob("local_*.json"):
                audit = ws_dir / meta.stem / "audit.jsonl"
                if audit.exists():
                    yield meta, audit, ws_dir.name


def main() -> int:
    target = parse_target_date()
    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = DATA_ROOT / f"sessions_{target.isoformat()}_runAt_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict[str, Any]] = []
    scanned = matched = 0
    for meta_path, audit_path, ws_id in discover_sessions(SOURCE_LOG_ROOT):
        scanned += 1
        meta = load_meta(meta_path)
        if not session_touches_date(meta, target):
            continue
        matched += 1
        summary, turns, rate_limits = parse_session(meta_path, audit_path, ws_id)
        out_path = write_session(out_dir, summary, turns, rate_limits)
        index.append({
            "session_id": summary.session_id,
            "title": summary.title,
            "model": summary.model,
            "created_at": summary.created_at,
            "duration_seconds": summary.duration_seconds,
            "total_turns": summary.total_turns,
            "total_actions": summary.total_actions,
            "file": out_path.name,
        })
        print(f"  + {summary.process_name or summary.session_id} -> {out_path.name}")

    (out_dir / "_index.json").write_text(
        json.dumps({
            "target_date": target.isoformat(),
            "run_at": run_ts,
            "source_root": str(SOURCE_LOG_ROOT),
            "scanned": scanned,
            "matched": matched,
            "sessions": index,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nDone. {matched}/{scanned} sessions matched {target} -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
