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
