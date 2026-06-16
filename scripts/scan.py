"""Scan Claude cowork session logs for a given date and emit per-session JSONL.

Output is designed for an LLM-as-judge that extracts personalized skills from
recurring action patterns. See docs/data_goal.md for the field rationale.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


SOURCE_COWORK = "claude-cowork"
SOURCE_CLAUDE_CODE = "claude-code"


def _detect_log_root(source: str = SOURCE_COWORK) -> Path:
    """Auto-detect the log root for the chosen source on the current OS.

    Priority:
      1. CLAUDE_LOG_ROOT env var (absolute override; applies to the chosen source)
      2. claude-cowork → Claude Desktop local-agent-mode-sessions
         (Win: glob AppData/Local/Packages/Claude_*/...; mac: Application Support;
          Linux: ~/.config/Claude)
      3. claude-code   → ~/.claude/projects (cross-platform)

    Raises SystemExit with a helpful message if nothing is found so the user
    knows exactly what to set.
    """
    env = os.environ.get("CLAUDE_LOG_ROOT", "").strip()
    if env:
        return Path(env)

    home = Path.home()

    if source == SOURCE_CLAUDE_CODE:
        candidates = [home / ".claude" / "projects"]
        layout = "<encoded-cwd>/<sessionId>.jsonl"
    elif sys.platform == "win32":
        packages = home / "AppData" / "Local" / "Packages"
        # Glob handles any Claude_<suffix> package family name.
        candidates = sorted(packages.glob(
            "Claude_*/LocalCache/Roaming/Claude/local-agent-mode-sessions"
        ))
        layout = "<userId>/<workspaceId>/local_<sessionId>/audit.jsonl"
    elif sys.platform == "darwin":
        candidates = [home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"]
        layout = "<userId>/<workspaceId>/local_<sessionId>/audit.jsonl"
    else:
        candidates = [home / ".config" / "Claude" / "local-agent-mode-sessions"]
        layout = "<userId>/<workspaceId>/local_<sessionId>/audit.jsonl"

    for p in candidates:
        if p.exists():
            return p

    raise SystemExit(
        f"[scan] Could not find {source} logs on this machine.\n"
        f"Set CLAUDE_LOG_ROOT=<path> to the folder that contains {layout}"
    )


# ── CONFIG ────────────────────────────────────────────────────────────────────

# Định dạng TARGET_DATE:
#   - Bỏ trống ("" / None)      → ngày hôm nay
#   - "ALL"                     → quét tất cả session (không lọc ngày)
#   - "YYYY-MM-DD"              → đúng 1 ngày cụ thể
#   - "YYYY-MM-DD, YYYY-MM-DD"  → nhiều ngày, cách nhau bởi dấu phẩy
# Một session được giữ nếu cửa sổ [createdAt, lastActivityAt] chạm bất kỳ ngày nào.
TARGET_DATE = "2026-06-15"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_data_root() -> Path:
    """Trả về data dir phù hợp với cả dev mode và frozen .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "pattern_data"
    return Path(__file__).resolve().parent.parent / "data"


DATA_ROOT = _get_data_root()

# ── Structural feedback signals ───────────────────────────────────────────────
#
# Feedback is derived from turn/action *structure* + tool outcomes, not phrase
# lists, so it holds across languages:
#   - `repeat` (rework) = retrying a tool that just FAILED (within the window).
#     Clean autonomous loops (screenshot×N) succeed, so they don't count.
#   - `failure_count` = actions whose tool_result was an error (result_ok False).

REWORK_WINDOW_SECONDS = 60

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
    feedback_flag: str | None = None  # "repeat" (rework after a failure)
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
    skills_enabled: bool | None
    plugins_enabled: bool | None
    available_slash_commands: list[str]
    focused_apps: list[str]
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
    failure_count: int
    repeat_count: int
    rate_limit_hits: int
    outputs_produced: int
    outputs_names: list[str]
    uploads_produced: int
    upload_names: list[str]


# ── Utilities ─────────────────────────────────────────────────────────────────


def parse_target_dates(raw: str | None = None) -> list[date] | None:
    """Resolve the target-date spec into the dates to include.

    `raw` defaults to the module TARGET_DATE constant (None falls back to it).
    Returns a list of dates, or None to mean "scan all sessions" (no filter).
    See the TARGET_DATE comment in CONFIG for the accepted formats.
    """
    raw = (TARGET_DATE if raw is None else raw).strip()
    if not raw:
        return [datetime.now().date()]
    if raw.upper() == "ALL":
        return None
    return [
        datetime.strptime(part.strip(), "%Y-%m-%d").date()
        for part in raw.split(",")
        if part.strip()
    ]


def target_label(targets: list[date] | None) -> str:
    """Filename-safe label for the resolved target dates."""
    if targets is None:
        return "ALL"
    return "+".join(t.isoformat() for t in targets)


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


# Computer-use prompts embed the focused window as:
#   <cu_window_hints>The user is pointing at: window "Title - App" (...)</cu_window_hints>
# We keep the quoted window title — a stable per-user domain marker (L5).
_WINDOW_HINT_RE = re.compile(
    r'<cu_window_hints>.*?pointing at:\s*window\s*"([^"]+)"', re.DOTALL
)


def extract_window_hints(text: str | None) -> list[str]:
    """Return window titles named in any `<cu_window_hints>` blocks in `text`."""
    if not text:
        return []
    return _WINDOW_HINT_RE.findall(text)


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


def mark_rework_turns(
    turns: list[TurnRecord], window_seconds: float = REWORK_WINDOW_SECONDS
) -> None:
    """Flag assistant turns that re-run a tool which recently FAILED — genuine
    rework, not normal repetition.

    A turn is `repeat` when it uses a tool whose prior run (in an earlier turn,
    within the window) returned an error (result_ok is False). Clean autonomous
    loops — screenshot×N, TaskCreate×N — succeed every time, so they never count.
    Needs `result_ok` populated, so it runs as a post-pass. Mutates in place."""
    recent_fail: dict[str, datetime] = {}
    for turn in turns:
        if turn.role != "assistant":
            continue
        dt = iso_to_dt(turn.ts)
        if dt:
            for a in turn.actions:
                prev = recent_fail.get(a.tool_name)
                if (
                    prev is not None
                    and (dt - prev).total_seconds() <= window_seconds
                    and turn.feedback_flag is None
                ):
                    turn.feedback_flag = "repeat"
                    break
        # Record this turn's failures so a *later* turn can be flagged as rework.
        if dt:
            for a in turn.actions:
                if a.result_ok is False:
                    recent_fail[a.tool_name] = dt


# ── Session parsing ───────────────────────────────────────────────────────────


def load_meta(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def session_touches_dates(meta: dict[str, Any], targets: list[date] | None) -> bool:
    # None = ALL: keep every session regardless of its date window.
    if targets is None:
        return True
    created = epoch_ms_to_date(meta.get("createdAt"))
    last = epoch_ms_to_date(meta.get("lastActivityAt"))
    start = created or last
    end = last or created
    if not (start and end):
        return False
    return any(start <= t <= end for t in targets)


def build_summary(
    meta: dict[str, Any],
    events: Iterable[dict[str, Any]],
    artifact_dir: Path | None,
    workspace_id: str,
    *,
    skip_sidechain: bool = False,
) -> tuple[SessionSummary, list[TurnRecord], list[dict[str, Any]]]:
    """Turn a stream of audit/transcript events + a metadata dict into the
    three-layer session record. Shared by both log sources (cowork audit.jsonl
    and Claude Code transcripts); only discovery + meta assembly differ.

    `artifact_dir` is the folder holding `outputs/` and `uploads/` (cowork);
    pass None when the source has no such artifacts (Claude Code).
    `skip_sidechain` drops sub-agent turns (`isSidechain`) — used for Claude
    Code so only the user-driven trajectory is mined.
    """
    turns: list[TurnRecord] = []
    rate_limits: list[dict[str, Any]] = []
    tool_usage: dict[str, int] = {}
    tool_sequence: list[str] = []
    mcp_usage: dict[str, int] = {}
    actions_by_tool_use_id: dict[str, ActionRecord] = {}
    seen_uuids: set[str] = set()
    focused_apps: list[str] = []
    turn_idx = 0

    for event in events:
        if not isinstance(event, dict):
            continue

        # Drop sub-agent sidechain turns when requested (Claude Code).
        if skip_sidechain and event.get("isSidechain"):
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
        # `isMeta` user events are system-injected reminders (Claude Code), not
        # the user's own turn — skip them so intent/turns stay clean.
        if etype == "user" and not event.get("isReplay") and not event.get("isMeta"):
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
            for app in extract_window_hints(text):
                if app not in focused_apps:
                    focused_apps.append(app)
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

    # Structural feedback: flag assistant turns that reworked a failed tool.
    mark_rework_turns(turns)

    # Outcome / artifact signals — names of files Claude produced (outputs/) and
    # files the user brought in (uploads/). Names reveal artifact type (xlsx,
    # png, pptx…) which a bare count can't; see data_goal L5/L7.
    def _file_names(folder: Path) -> list[str]:
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.rglob("*") if p.is_file())

    outputs_names = _file_names(artifact_dir / "outputs") if artifact_dir else []
    upload_names = _file_names(artifact_dir / "uploads") if artifact_dir else []

    duration = None
    if meta.get("createdAt") and meta.get("lastActivityAt"):
        duration = (meta["lastActivityAt"] - meta["createdAt"]) / 1000.0

    summary = SessionSummary(
        session_id=meta.get("sessionId") or "session",
        title=meta.get("title"),
        intent_seed=truncate(meta.get("initialMessage") or "", 1000) or None,
        model=meta.get("model"),
        process_name=meta.get("processName"),
        workspace_id=workspace_id,
        user_selected_folders=meta.get("userSelectedFolders") or [],
        skills_enabled=meta.get("skillsEnabled"),
        plugins_enabled=meta.get("pluginsEnabled"),
        available_slash_commands=meta.get("slashCommands") or [],
        focused_apps=focused_apps,
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
        failure_count=sum(
            1 for t in turns for a in t.actions if a.result_ok is False
        ),
        repeat_count=sum(1 for t in turns if t.feedback_flag == "repeat"),
        rate_limit_hits=len(rate_limits),
        outputs_produced=len(outputs_names),
        outputs_names=outputs_names,
        uploads_produced=len(upload_names),
        upload_names=upload_names,
    )
    return summary, turns, rate_limits


def parse_session(
    meta_path: Path, audit_path: Path, workspace_id: str
) -> tuple[SessionSummary, list[TurnRecord], list[dict[str, Any]]]:
    """Cowork entry: load the sidecar metadata + audit.jsonl, then build."""
    meta = load_meta(meta_path)
    meta.setdefault("sessionId", meta_path.stem)
    return build_summary(meta, iter_jsonl(audit_path), audit_path.parent, workspace_id)


# ── Claude Code source (~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl) ────
#
# Claude Code transcripts share the inner message format with cowork audit.jsonl
# but carry no sidecar metadata file and no outputs/uploads folders. We rebuild
# an equivalent `meta` dict from the transcript so `build_summary` can be reused.

_CMD_WRAPPER_PREFIXES = ("<command-name>", "<command-message>", "<local-command")


def _is_real_user_turn(event: dict[str, Any]) -> bool:
    """True for a user's own prompt — not a system reminder, sidechain, slash
    command wrapper, or a wrapped tool_result envelope."""
    if event.get("type") != "user" or event.get("isMeta") or event.get("isSidechain"):
        return False
    content = event.get("message", {}).get("content")
    if isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
    ):
        return False
    text = (extract_user_text(content) or "").lstrip()
    return bool(text) and not text.startswith(_CMD_WRAPPER_PREFIXES)


def build_cc_meta(transcript_path: Path) -> dict[str, Any]:
    """Assemble a cowork-shaped metadata dict from a Claude Code transcript:
    title (ai-title), intent (first real user turn), model (first assistant),
    and createdAt/lastActivityAt as epoch ms (min/max event timestamp)."""
    title: str | None = None
    intent: str | None = None
    model: str | None = None
    cwd: str | None = None
    ts_min: int | None = None
    ts_max: int | None = None

    for event in iter_jsonl(transcript_path):
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        if etype == "ai-title" and event.get("aiTitle"):
            title = event["aiTitle"]
        cwd = cwd or event.get("cwd")
        dt = iso_to_dt(event.get("timestamp"))
        if dt:
            ms = int(dt.timestamp() * 1000)
            ts_min = ms if ts_min is None else min(ts_min, ms)
            ts_max = ms if ts_max is None else max(ts_max, ms)
        if intent is None and _is_real_user_turn(event):
            intent = extract_user_text(event.get("message", {}).get("content"))
        if model is None and etype == "assistant":
            model = (event.get("message") or {}).get("model")

    return {
        "sessionId": transcript_path.stem,
        "title": title,
        "initialMessage": intent,
        "model": model,
        "processName": (cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                        if cwd else None),
        "createdAt": ts_min,
        "lastActivityAt": ts_max,
    }


def parse_claude_code_session(
    transcript_path: Path, workspace_id: str, meta: dict[str, Any] | None = None
) -> tuple[SessionSummary, list[TurnRecord], list[dict[str, Any]]]:
    """Claude Code entry: rebuild meta from the transcript, then build. Excludes
    sub-agent sidechain turns; has no outputs/uploads artifacts."""
    meta = meta or build_cc_meta(transcript_path)
    return build_summary(
        meta, iter_jsonl(transcript_path), None, workspace_id, skip_sidechain=True
    )


def discover_claude_code_sessions(root: Path) -> Iterable[tuple[Path, str]]:
    """Yield (transcript_path, workspace_id) for every session under every
    project folder in ~/.claude/projects."""
    if not root.exists():
        return
    for proj_dir in sorted(root.iterdir()):
        if not proj_dir.is_dir():
            continue
        for transcript in sorted(proj_dir.glob("*.jsonl")):
            yield transcript, proj_dir.name


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


def _iter_parsed(
    source: str, root: Path, targets: list[date] | None
) -> Iterator[tuple[SessionSummary, list[TurnRecord], list[dict[str, Any]], bool]]:
    """Yield (summary, turns, rate_limits, matched) per discovered session for
    the chosen source. `matched` is False for sessions filtered out by date —
    surfaced so the caller can count scanned vs matched uniformly."""
    if source == SOURCE_CLAUDE_CODE:
        for transcript, ws_id in discover_claude_code_sessions(root):
            meta = build_cc_meta(transcript)
            if not session_touches_dates(meta, targets):
                yield None, None, None, False
                continue
            yield (*parse_claude_code_session(transcript, ws_id, meta), True)
    else:
        for meta_path, audit_path, ws_id in discover_sessions(root):
            meta = load_meta(meta_path)
            if not session_touches_dates(meta, targets):
                yield None, None, None, False
                continue
            yield (*parse_session(meta_path, audit_path, ws_id), True)


def run_scan(
    source: str = SOURCE_COWORK,
    target_date: str | None = None,
    log_fn=print,
) -> Path:
    """Scan sessions và write JSONL ra out_dir. Trả về out_dir path."""
    root = _detect_log_root(source)
    targets = parse_target_dates(target_date)
    label = target_label(targets)
    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = DATA_ROOT / f"sessions_{label}_runAt_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log_fn(f"Quét {source} tại {root}")
    log_fn(f"Lọc ngày: {label}")

    index: list[dict[str, Any]] = []
    scanned = matched = 0
    for summary, turns, rate_limits, ok in _iter_parsed(source, root, targets):
        scanned += 1
        if not ok:
            continue
        matched += 1
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
        log_fn(f"  + {summary.process_name or summary.session_id} -> {out_path.name}")

    (out_dir / "_index.json").write_text(
        json.dumps({
            "source": source,
            "target_date": label,
            "run_at": run_ts,
            "source_root": str(root),
            "scanned": scanned,
            "matched": matched,
            "sessions": index,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log_fn(f"\nDone. {matched}/{scanned} {source} sessions matched {label} -> {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Claude session logs -> per-session JSONL.")
    parser.add_argument(
        "--source", choices=[SOURCE_COWORK, SOURCE_CLAUDE_CODE], default=SOURCE_COWORK,
        help="Log source: claude-cowork (Desktop audit.jsonl, default) or claude-code (~/.claude/projects).",
    )
    parser.add_argument(
        "--target-date", default=None, metavar="SPEC",
        help='Override TARGET_DATE: "" (today), "ALL", "YYYY-MM-DD", or comma-separated dates.',
    )
    args = parser.parse_args(argv)
    run_scan(source=args.source, target_date=args.target_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
