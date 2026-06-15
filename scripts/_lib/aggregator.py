"""Rule-based session clustering for Pattern's Lượt 2 judge stage.

Pure Python. No LLM. Takes per-session JSONL produced by scripts/scan.py and
groups sessions whose behaviour looks similar, so the judge prompt sees small
focused clusters instead of raw noise.
"""

from __future__ import annotations

import json
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
    retry_count: int
    correction_count: int
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
            retry_count=int(rec.get("retry_count") or 0),
            correction_count=int(rec.get("correction_count") or 0),
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


import re
import unicodedata


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_title(title: str | None) -> frozenset[str]:
    if not title:
        return frozenset()
    folded = unicodedata.normalize("NFC", title).lower()
    stripped = _PUNCT_RE.sub(" ", folded)
    tokens = [t for t in stripped.split() if len(t) >= 2]
    return frozenset(tokens)


def subcluster_by_title(
    sessions: Iterable[Session],
    *,
    jaccard_threshold: float = 0.5,
) -> list[list[Session]]:
    """Sub-cluster by title token Jaccard. Sessions with missing/empty titles
    are never grouped together (defensive: avoid false positives)."""
    groups: list[list[Session]] = []
    keys: list[frozenset[str]] = []
    for session in sessions:
        key = _normalize_title(session.title)
        if not key:
            groups.append([session])
            keys.append(key)
            continue
        placed = False
        for idx, repr_key in enumerate(keys):
            if repr_key and _jaccard(key, repr_key) >= jaccard_threshold:
                groups[idx].append(session)
                keys[idx] = repr_key | key
                placed = True
                break
        if not placed:
            groups.append([session])
            keys.append(key)
    return groups


def filter_by_size(
    clusters: Iterable[list[Session]], *, min_size: int
) -> list[list[Session]]:
    return [c for c in clusters if len(c) >= min_size]


@dataclass
class Cluster:
    sessions: list[Session]
    representative_tools: list[str]
    representative_titles: list[str]
    recurrence: int
    retry_rate: float
    correction_rate: float
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
            "retry_rate": round(self.retry_rate, 3),
            "correction_rate": round(self.correction_rate, 3),
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "total_tokens": self.total_tokens,
            "behavior_class_hint": self.behavior_class_hint,
            "top_tools_per_session": [
                dict(sorted(s.tool_usage.items(), key=lambda kv: -kv[1])[:5])
                for s in self.sessions
            ],
            "titles": [s.title for s in self.sessions],
        }


def _classify(retry_rate: float, recurrence: int) -> str:
    if retry_rate >= 0.2:
        return "inefficient"
    if retry_rate < 0.1 and recurrence >= 3:
        return "process"
    return "unclear"


def _build_cluster(group: list[Session]) -> Cluster:
    n = len(group)
    retry_rate = (
        sum(s.retry_count / s.total_actions for s in group if s.total_actions)
        / max(1, sum(1 for s in group if s.total_actions))
    )
    correction_rate = (
        sum(s.correction_count / s.total_user_turns for s in group if s.total_user_turns)
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
        retry_rate=retry_rate,
        correction_rate=correction_rate,
        avg_duration_seconds=avg_duration,
        total_tokens=total_tokens,
        behavior_class_hint=_classify(retry_rate, n),
    )


def aggregate(
    sessions: list[Session],
    *,
    min_size: int = 2,
    top_n: int = 3,
    tool_threshold: float = 0.6,
    title_threshold: float = 0.5,
) -> list[Cluster]:
    """End-to-end clustering pipeline: tool ngram → title sub-cluster → filter → metrics."""
    tool_clusters = cluster_by_tool_ngram(
        sessions, top_n=top_n, jaccard_threshold=tool_threshold
    )
    refined: list[list[Session]] = []
    for tc in tool_clusters:
        refined.extend(subcluster_by_title(tc, jaccard_threshold=title_threshold))
    sized = filter_by_size(refined, min_size=min_size)
    return [_build_cluster(g) for g in sized]
