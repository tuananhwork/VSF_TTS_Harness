"""Tests for scripts/_lib/aggregator.py."""

from __future__ import annotations

from pathlib import Path

from _lib.aggregator import (
    Cluster,
    Session,
    aggregate,
    cluster_by_tool_ngram,
    load_sessions,
)


def _mk_session(
    sid: str, tools: dict[str, int], title: str = "x", intent_seed: str | None = None,
    tool_sequence: list[str] | None = None,
) -> Session:
    return Session(
        session_id=sid, process_name=sid, title=title, intent_seed=intent_seed,
        total_actions=sum(tools.values()), total_user_turns=0,
        total_input_tokens=0, total_output_tokens=0, duration_seconds=0.0,
        tool_usage=tools, retry_count=0, correction_count=0,
        tool_sequence=tool_sequence or [],
    )


def test_to_dict_includes_tool_sequence_per_session() -> None:
    a = _mk_session("a", {"Read": 1, "Edit": 2}, tool_sequence=["Read", "Edit×2"])
    cluster = aggregate([a])[0]
    d = cluster.to_dict()
    assert d["tool_sequence_per_session"] == [["Read", "Edit×2"]]


def test_load_sessions_reads_all_fixture_files(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    assert len(sessions) == 4
    assert all(isinstance(s, Session) for s in sessions)


def test_load_sessions_extracts_title_and_tools(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    titles = {s.title for s in sessions}
    assert "Computer use capabilities test" in titles
    fermat = next(s for s in sessions if s.process_name == "lucid-beautiful-fermat")
    assert fermat.total_actions > 0
    assert len(fermat.tool_usage) > 0


def test_ngram_groups_sessions_sharing_top3_tools() -> None:
    a = _mk_session("a", {"scan": 5, "edit": 4, "test": 3, "noise": 1})
    b = _mk_session("b", {"scan": 6, "edit": 2, "test": 1})
    c = _mk_session("c", {"send_mail": 3, "calendar": 2, "search": 1})
    clusters = cluster_by_tool_ngram([a, b, c], top_n=3, jaccard_threshold=0.6)
    cluster_sets = [{s.session_id for s in cl} for cl in clusters]
    assert {"a", "b"} in cluster_sets
    assert {"c"} in cluster_sets


def test_ngram_jaccard_below_threshold_splits() -> None:
    # share 1 of 3 → Jaccard = 1/5 = 0.2 → separate clusters
    a = _mk_session("a", {"x": 3, "y": 2, "z": 1})
    b = _mk_session("b", {"x": 3, "p": 2, "q": 1})
    clusters = cluster_by_tool_ngram([a, b], top_n=3, jaccard_threshold=0.6)
    assert len(clusters) == 2


def test_ngram_handles_fewer_than_topn_tools() -> None:
    a = _mk_session("a", {"x": 1})
    b = _mk_session("b", {"x": 1})
    clusters = cluster_by_tool_ngram([a, b], top_n=3, jaccard_threshold=0.6)
    assert len(clusters) == 1
    assert {s.session_id for s in clusters[0]} == {"a", "b"}


def test_aggregate_returns_clusters_with_metrics(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    clusters = aggregate(sessions)
    assert all(isinstance(c, Cluster) for c in clusters)
    assert all(c.recurrence >= 1 for c in clusters)
    # at least one cluster contains the high-retry fermat session
    fermat_in = any(
        any(s.process_name == "lucid-beautiful-fermat" for s in c.sessions)
        for c in clusters
    )
    assert fermat_in


def test_aggregate_metrics_classify_inefficient() -> None:
    high_retry = _mk_session(
        "h", {"click": 14}, title="Computer test",
    )
    high_retry = Session(
        session_id="h", process_name="h", title="Computer test", intent_seed=None,
        total_actions=14, total_user_turns=5, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=10.0,
        tool_usage={"click": 14}, retry_count=13, correction_count=0,
    )
    other = Session(
        session_id="h2", process_name="h2", title="Computer test", intent_seed=None,
        total_actions=10, total_user_turns=5, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=10.0,
        tool_usage={"click": 10}, retry_count=8, correction_count=0,
    )
    clusters = aggregate([high_retry, other])
    assert len(clusters) == 1
    assert clusters[0].behavior_class_hint == "inefficient"
    assert clusters[0].retry_rate > 0.2


def test_aggregate_includes_singleton_groups(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    clusters = aggregate(sessions)
    # Loose tool-usage grouping only — no title gate, so all sessions appear
    # somewhere even if their group has size 1.
    total = sum(c.recurrence for c in clusters)
    assert total == len(sessions)


def test_to_dict_includes_cleaned_intent_seeds() -> None:
    a = _mk_session(
        "a", {"Read": 1}, title="ConvMixer file summary",
        intent_seed="<uploaded_files>\n<file>...</file>\n</uploaded_files>\n\nTóm tắt file",
    )
    cluster = aggregate([a])[0]
    d = cluster.to_dict()
    assert d["intent_seeds"] == ["Tóm tắt file"]
