"""Rule-based session pre-grouping for Pattern's Lượt 2 judge stage.

Pure Python. No LLM. Takes per-session JSONL produced by scripts/scan.py and
does a loose grouping by tool usage so the judge prompt sees manageable
chunks. Whether sessions across groups share the *same intent* (e.g. "Tóm
tắt file ..." regardless of which file/title) is left to the LLM judge, since
titles are auto-generated per session and vary even for the same task.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Session:
    """A flattened view of one session, drawn from its session_summary record."""

    session_id: str
    process_name: str | None
    title: str | None
    intent_seed: str | None
    total_actions: int
    total_user_turns: int
    total_input_tokens: int
    total_output_tokens: int
    duration_seconds: float | None
    tool_usage: dict[str, int]
    repeat_count: int
    pivot_count: int
    tool_sequence: list[str] = field(default_factory=list)
    source_file: str = ""


def _read_summary(jsonl_path: Path) -> dict | None:
    with jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("record_type") == "session_summary":
                return rec
    return None


def load_sessions(sessions_dir: Path) -> list[Session]:
    sessions: list[Session] = []
    for jsonl_path in sorted(sessions_dir.glob("*.jsonl")):
        rec = _read_summary(jsonl_path)
        if not rec:
            continue
        sessions.append(Session(
            session_id=rec.get("session_id", jsonl_path.stem),
            process_name=rec.get("process_name"),
            title=rec.get("title"),
            intent_seed=rec.get("intent_seed"),
            total_actions=int(rec.get("total_actions") or 0),
            total_user_turns=int(rec.get("total_user_turns") or 0),
            total_input_tokens=int(rec.get("total_input_tokens") or 0),
            total_output_tokens=int(rec.get("total_output_tokens") or 0),
            duration_seconds=rec.get("duration_seconds"),
            tool_usage=dict(rec.get("tool_usage") or {}),
            repeat_count=int(rec.get("repeat_count") or 0),
            pivot_count=int(rec.get("pivot_count") or 0),
            tool_sequence=list(rec.get("tool_sequence") or []),
            source_file=jsonl_path.name,
        ))
    return sessions


def _top_n_tools(session: Session, n: int) -> frozenset[str]:
    sorted_tools = sorted(
        session.tool_usage.items(), key=lambda kv: (-kv[1], kv[0])
    )
    return frozenset(name for name, _ in sorted_tools[:n])


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cluster_by_tool_ngram(
    sessions: Iterable[Session],
    *,
    top_n: int = 3,
    jaccard_threshold: float = 0.6,
) -> list[list[Session]]:
    """Greedy single-pass clustering by overlap of each session's top-N tools.

    Each session is added to the first existing cluster whose representative
    set has Jaccard >= threshold; otherwise it starts a new cluster.
    """
    clusters: list[list[Session]] = []
    cluster_keys: list[frozenset[str]] = []
    for session in sessions:
        key = _top_n_tools(session, top_n)
        placed = False
        for idx, repr_key in enumerate(cluster_keys):
            if _jaccard(key, repr_key) >= jaccard_threshold:
                clusters[idx].append(session)
                cluster_keys[idx] = repr_key | key  # union as representative
                placed = True
                break
        if not placed:
            clusters.append([session])
            cluster_keys.append(key)
    return clusters


_UPLOADED_FILES_RE = re.compile(r"<uploaded_files>.*?</uploaded_files>", re.DOTALL)


def _clean_intent(text: str | None) -> str | None:
    """Strip the `<uploaded_files>...</uploaded_files>` block (file paths and
    uuids differ on every upload, so they'd block the LLM from recognizing
    the same intent across sessions) and surrounding whitespace."""
    if not text:
        return text
    cleaned = _UPLOADED_FILES_RE.sub("", text).strip()
    return cleaned or text.strip()


@dataclass
class Cluster:
    sessions: list[Session]
    representative_tools: list[str]
    representative_titles: list[str]
    recurrence: int
    repeat_rate: float
    pivot_rate: float
    avg_duration_seconds: float
    total_tokens: int
    behavior_class_hint: str  # "process" | "inefficient" | "unclear"

    def to_dict(self) -> dict:
        return {
            "session_ids": [s.session_id for s in self.sessions],
            "process_names": [s.process_name for s in self.sessions],
            "source_files": [s.source_file for s in self.sessions],
            "representative_tools": self.representative_tools,
            "representative_titles": self.representative_titles,
            "recurrence": self.recurrence,
            "repeat_rate": round(self.repeat_rate, 3),
            "pivot_rate": round(self.pivot_rate, 3),
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "total_tokens": self.total_tokens,
            "behavior_class_hint": self.behavior_class_hint,
            "top_tools_per_session": [
                dict(sorted(s.tool_usage.items(), key=lambda kv: -kv[1])[:5])
                for s in self.sessions
            ],
            "titles": [s.title for s in self.sessions],
            "intent_seeds": [_clean_intent(s.intent_seed) for s in self.sessions],
            "tool_sequence_per_session": [s.tool_sequence for s in self.sessions],
        }


def _classify(repeat_rate: float, recurrence: int) -> str:
    if repeat_rate >= 0.2:
        return "inefficient"
    if repeat_rate < 0.1 and recurrence >= 3:
        return "process"
    return "unclear"


def _build_cluster(group: list[Session]) -> Cluster:
    n = len(group)
    repeat_rate = (
        sum(s.repeat_count / s.total_actions for s in group if s.total_actions)
        / max(1, sum(1 for s in group if s.total_actions))
    )
    pivot_rate = (
        sum(s.pivot_count / s.total_user_turns for s in group if s.total_user_turns)
        / max(1, sum(1 for s in group if s.total_user_turns))
    )
    avg_duration = sum((s.duration_seconds or 0.0) for s in group) / n
    total_tokens = sum(s.total_input_tokens + s.total_output_tokens for s in group)
    # Representative tools = union of top-3 across the group
    rep_tools: set[str] = set()
    for s in group:
        rep_tools |= _top_n_tools(s, 3)
    return Cluster(
        sessions=group,
        representative_tools=sorted(rep_tools),
        representative_titles=[s.title for s in group if s.title],
        recurrence=n,
        repeat_rate=repeat_rate,
        pivot_rate=pivot_rate,
        avg_duration_seconds=avg_duration,
        total_tokens=total_tokens,
        behavior_class_hint=_classify(repeat_rate, n),
    )


def aggregate(
    sessions: list[Session],
    *,
    top_n: int = 3,
    tool_threshold: float = 0.6,
) -> list[Cluster]:
    """Loose pre-grouping by tool-usage n-gram, with per-group metrics.

    Groups (including singletons) are all passed through — recognizing
    whether two groups represent the same recurring intent (e.g. same
    "summarize uploaded file" request with different auto-generated titles)
    is left to the LLM judge.
    """
    tool_clusters = cluster_by_tool_ngram(
        sessions, top_n=top_n, jaccard_threshold=tool_threshold
    )
    return [_build_cluster(g) for g in tool_clusters]
