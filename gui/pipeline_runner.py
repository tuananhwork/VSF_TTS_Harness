"""Background pipeline thread + message protocol cho Pattern GUI."""
from __future__ import annotations

import json
import queue
import shutil
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

# Thêm scripts/ vào path để import scan, judge, synth (chỉ cần trong dev mode;
# trong frozen .exe PyInstaller đã bundle tất cả vào sys._MEIPASS)
if not getattr(sys, "frozen", False):
    _SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))

import scan as _scan
import judge as _judge
import synth as _synth


@dataclass
class PipelineParams:
    date: str           # "YYYY-MM-DD" hoặc "" (hôm nay)
    source: str         # "claude-cowork" | "claude-code"
    min_recurrence: int = 2
    max_deepdive: int = 5
    top_candidates: int = 5
    timeout: float = 300.0


@dataclass
class SkillProposal:
    name: str
    description: str
    recurrence: int
    confidence: str     # "cao" | "trung bình" | "thấp"
    folder_path: Path
    has_quality_issues: bool = False


# Queue message types:
#   ("log", str)                     — log line
#   ("step_start", str)              — "scan" | "judge" | "synth"
#   ("step_done", str)               — step succeeded
#   ("step_error", str, str)         — step name, error message
#   ("done", list[SkillProposal])    — pipeline finished
#   ("no_sessions", None)            — 0 sessions found
#   ("no_candidates", None)          — 0 patterns found


def _score_to_confidence(candidate: dict) -> str:
    score = sum(candidate.get("final_score", candidate.get("prelim_score", {})).values())
    if score >= 6:
        return "cao"
    if score >= 3:
        return "trung bình"
    return "thấp"


def _to_proposals(results: list[dict], out_dir: Path) -> list[SkillProposal]:
    proposals = []
    for c in results:
        folder = out_dir / c["name"]
        if not folder.exists():
            continue
        proposals.append(SkillProposal(
            name=c["name"],
            description=c.get("trigger_intent") or c.get("name", ""),
            recurrence=c.get("metrics", {}).get("recurrence", 0),
            confidence=_score_to_confidence(c),
            folder_path=folder,
            has_quality_issues=bool(c.get("synth_problems")),
        ))
    return proposals


class PipelineRunner(threading.Thread):
    def __init__(self, params: PipelineParams, q: queue.Queue):
        super().__init__(daemon=True)
        self._params = params
        self._q = q
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _log(self, msg: str) -> None:
        self._q.put(("log", msg))

    def run(self) -> None:
        p = self._params

        # ── Scan ────────────────────────────────────────────────
        self._q.put(("step_start", "scan"))
        try:
            sessions_dir = _scan.run_scan(
                source=p.source,
                target_date=p.date,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "scan", str(e)))
            return

        index_path = sessions_dir / "_index.json"
        if index_path.exists():
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            if idx.get("matched", 0) == 0:
                self._q.put(("step_done", "scan"))
                self._q.put(("no_sessions", None))
                return

        self._q.put(("step_done", "scan"))
        if self._cancelled.is_set():
            return

        # ── Judge ────────────────────────────────────────────────
        self._q.put(("step_start", "judge"))
        try:
            candidates_path = _judge.run_judge(
                sessions_dir=sessions_dir,
                min_recurrence=p.min_recurrence,
                max_deepdive=p.max_deepdive,
                top_candidates=p.top_candidates,
                timeout=p.timeout,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "judge", str(e)))
            return

        self._q.put(("step_done", "judge"))
        if self._cancelled.is_set():
            return

        # ── Synth ────────────────────────────────────────────────
        self._q.put(("step_start", "synth"))
        try:
            results, out_dir = _synth.run_synth(
                candidates_path=candidates_path,
                top=p.top_candidates,
                timeout=p.timeout,
                log_fn=self._log,
            )
        except Exception as e:
            self._q.put(("step_error", "synth", str(e)))
            return

        self._q.put(("step_done", "synth"))

        if not results:
            self._q.put(("no_candidates", None))
            return

        proposals = _to_proposals(results, out_dir)
        self._q.put(("done", proposals))


def install_skill(proposal: SkillProposal) -> None:
    """Copy skill folder vào ~/.claude/skills/<name>/."""
    skills_home = Path.home() / ".claude" / "skills"
    skills_home.mkdir(parents=True, exist_ok=True)
    dst = skills_home / proposal.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(proposal.folder_path, dst)
