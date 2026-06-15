"""Tests for scripts/_lib/aggregator.py."""

from __future__ import annotations

from pathlib import Path

from _lib.aggregator import (
    Session,
    cluster_by_tool_ngram,
    filter_by_size,
    load_sessions,
    subcluster_by_title,
)


def _mk_session(sid: str, tools: dict[str, int], title: str = "x") -> Session:
    return Session(
        session_id=sid, process_name=sid, title=title, intent_seed=None,
        total_actions=sum(tools.values()), total_user_turns=0,
        total_input_tokens=0, total_output_tokens=0, duration_seconds=0.0,
        tool_usage=tools, retry_count=0, correction_count=0,
    )


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


def test_subcluster_groups_similar_titles() -> None:
    a = _mk_session("a", {"x": 1}, title="Tóm tắt file PDF báo cáo")
    b = _mk_session("b", {"x": 1}, title="tóm tắt file PDF tài liệu!")
    c = _mk_session("c", {"x": 1}, title="Review code Python module utils")
    result = subcluster_by_title([a, b, c], jaccard_threshold=0.5)
    title_groups = [{s.session_id for s in g} for g in result]
    assert {"a", "b"} in title_groups
    assert {"c"} in title_groups


def test_subcluster_handles_missing_title() -> None:
    a = _mk_session("a", {"x": 1}, title=None)  # type: ignore[arg-type]
    b = _mk_session("b", {"x": 1}, title=None)  # type: ignore[arg-type]
    result = subcluster_by_title([a, b], jaccard_threshold=0.5)
    assert len(result) == 2  # missing titles never group


def test_filter_by_size_drops_below_threshold() -> None:
    g1 = [_mk_session("a", {}), _mk_session("b", {})]
    g2 = [_mk_session("c", {})]
    result = filter_by_size([g1, g2], min_size=2)
    assert result == [g1]
