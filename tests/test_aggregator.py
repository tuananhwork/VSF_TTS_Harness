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
        tool_usage=tools, repeat_count=0, failure_count=0,
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
        tool_usage={"click": 14}, repeat_count=13, failure_count=0,
    )
    other = Session(
        session_id="h2", process_name="h2", title="Computer test", intent_seed=None,
        total_actions=10, total_user_turns=5, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=10.0,
        tool_usage={"click": 10}, repeat_count=8, failure_count=0,
    )
    clusters = aggregate([high_retry, other])
    assert len(clusters) == 1
    assert clusters[0].behavior_class_hint == "inefficient"
    assert clusters[0].repeat_rate > 0.2


def test_aggregate_includes_singleton_groups(sessions_dir: Path) -> None:
    sessions = load_sessions(sessions_dir)
    clusters = aggregate(sessions)
    # Loose tool-usage grouping only — no title gate, so all sessions appear
    # somewhere even if their group has size 1.
    total = sum(c.recurrence for c in clusters)
    assert total == len(sessions)


def test_to_dict_surfaces_outputs_and_drops_dup_titles() -> None:
    s = Session(
        session_id="a", process_name="a", title="PRD", intent_seed=None,
        total_actions=1, total_user_turns=1, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0, tool_usage={"Write": 1},
        repeat_count=0, failure_count=0,
        outputs_names=["PRD.md"], focused_apps=["Figma"],
    )
    d = aggregate([s])[0].to_dict()
    assert d["outputs_per_session"] == [["PRD.md"]]          # artifact signal added
    assert d["focused_apps_per_session"] == [["Figma"]]      # domain signal added
    assert "representative_titles" not in d                  # duplicate title dropped
    assert d["titles"] == ["PRD"]                            # titles still present


def test_load_sessions_reads_outputs_and_focused_apps(tmp_path: Path) -> None:
    import json
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps({
        "record_type": "session_summary", "session_id": "a",
        "outputs_names": ["report.xlsx"], "focused_apps": ["Excel"],
    }) + "\n", encoding="utf-8")
    s = load_sessions(tmp_path)[0]
    assert s.outputs_names == ["report.xlsx"]
    assert s.focused_apps == ["Excel"]


def test_to_dict_includes_cleaned_intent_seeds() -> None:
    a = _mk_session(
        "a", {"Read": 1}, title="ConvMixer file summary",
        intent_seed="<uploaded_files>\n<file>...</file>\n</uploaded_files>\n\nTóm tắt file",
    )
    cluster = aggregate([a])[0]
    d = cluster.to_dict()
    assert d["intent_seeds"] == ["Tóm tắt file"]


def test_cluster_metrics_computes_rates_and_behavior() -> None:
    from _lib.aggregator import cluster_metrics
    a = Session(
        session_id="a", process_name="a", title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=3, failure_count=1,
    )
    b = Session(
        session_id="b", process_name="b", title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=3, failure_count=1,
    )
    m = cluster_metrics([a, b])
    assert m["recurrence"] == 2
    assert m["repeat_rate"] == 0.3        # mean(3/10, 3/10)
    assert m["failure_rate"] == 0.1       # mean(1/10, 1/10)
    assert m["behavior_class"] == "inefficient"   # repeat_rate >= 0.2


def _sess(sid: str, repeat: int, failure: int) -> Session:
    return Session(
        session_id=sid, process_name=sid, title="x", intent_seed=None,
        total_actions=10, total_user_turns=4, total_input_tokens=0,
        total_output_tokens=0, duration_seconds=0.0,
        tool_usage={"click": 10}, repeat_count=repeat, failure_count=failure,
    )


def test_recompute_uses_merged_evidence_not_tool_group() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    sessions = [_sess("s1", 0, 0), _sess("s2", 0, 0), _sess("s3", 0, 0)]
    # LLM merged 3 sessions into one candidate, though tool-ngram split them.
    cands = [{"name": "summarize",
              "evidence": {"session_ids": ["s1", "s2", "s3"]}}]
    out = recompute_candidate_metrics(cands, sessions)
    assert out[0]["metrics"]["recurrence"] == 3
    assert out[0]["metrics"]["behavior_class"] == "process"  # rec>=3, repeat<0.1
    assert out[0]["metrics"]["unknown_session_ids"] == []


def test_recompute_drops_hallucinated_session_ids() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    sessions = [_sess("s1", 0, 0)]
    cands = [{"name": "x", "evidence": {"session_ids": ["s1", "ghost"]}}]
    out = recompute_candidate_metrics(cands, sessions)
    assert out[0]["metrics"]["recurrence"] == 1            # only s1 is real
    assert out[0]["metrics"]["unknown_session_ids"] == ["ghost"]


def test_recompute_does_not_mutate_input() -> None:
    from _lib.aggregator import recompute_candidate_metrics
    cands = [{"name": "x", "evidence": {"session_ids": ["s1"]}}]
    recompute_candidate_metrics(cands, [_sess("s1", 0, 0)])
    assert "metrics" not in cands[0]
