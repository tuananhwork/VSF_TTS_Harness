"""Pattern GUI — main app entry point."""
from __future__ import annotations

import queue
import sys
import time
import threading
from pathlib import Path

import flet as ft

_GUI = Path(__file__).resolve().parent
if str(_GUI) not in sys.path:
    sys.path.insert(0, str(_GUI))

from pipeline_runner import PipelineParams, PipelineRunner, SkillProposal
from screen_configure import ConfigureScreen
from screen_running import RunningScreen
from screen_review import ReviewScreen


def main(page: ft.Page) -> None:
    page.title = "Pattern"
    page.window.width = 560
    page.window.height = 660
    page.window.min_width = 480
    page.window.min_height = 560
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 0

    _q: queue.Queue = queue.Queue()
    _runner: list[PipelineRunner | None] = [None]

    # Use a dict so inner functions can reference screens before they're created.
    # Functions capture the dict by reference; screens are populated below.
    _s: dict = {}

    # ── Navigation ───────────────────────────────────────────────────────────

    def _show_configure() -> None:
        page.controls.clear()
        page.controls.append(_s["configure"].container)
        page.update()

    def _show_running() -> None:
        page.controls.clear()
        page.controls.append(_s["running"].container)
        page.update()

    def _show_review(proposals: list[SkillProposal]) -> None:
        _s["review"].load_proposals(proposals)
        page.controls.clear()
        page.controls.append(_s["review"].container)
        page.update()

    # ── Pipeline control ─────────────────────────────────────────────────────

    def _start_pipeline(
        date: str, source: str, min_recurrence: int, max_deepdive: int
    ) -> None:
        nonlocal _q
        _q = queue.Queue()
        params = PipelineParams(
            date=date,
            source=source,
            min_recurrence=min_recurrence,
            max_deepdive=max_deepdive,
        )
        _s["running"].reset()
        _show_running()
        _runner[0] = PipelineRunner(params, _q)
        _runner[0].start()
        threading.Thread(target=_poll_queue, daemon=True).start()

    def _cancel_pipeline() -> None:
        if _runner[0]:
            _runner[0].cancel()
        _show_configure()

    # ── Queue polling (background thread) ────────────────────────────────────

    def _poll_queue() -> None:
        while _runner[0] and _runner[0].is_alive():
            _drain()
            time.sleep(0.05)
        _drain()  # final drain after thread ends

    def _drain() -> None:
        changed = False
        try:
            while True:
                msg = _q.get_nowait()
                _handle(msg)
                changed = True
        except queue.Empty:
            pass
        if changed:
            page.update()

    def _handle(msg: tuple) -> None:
        kind = msg[0]
        if kind == "log":
            _s["running"].append_log(msg[1])
        elif kind == "step_start":
            _s["running"].update_step("running", msg[1])
        elif kind == "step_done":
            _s["running"].update_step("done", msg[1])
        elif kind == "step_error":
            _s["running"].update_step("error", msg[1])
            _s["running"].append_error(msg[2])
        elif kind == "no_sessions":
            _s["running"].append_log("Không có session nào cho ngày này. Thử ngày khác.")
        elif kind == "no_candidates":
            _s["running"].append_log("Chưa phát hiện pattern đủ mạnh. Thử quét nhiều ngày hơn.")
        elif kind == "done":
            _show_review(msg[1])

    # ── Create screens (functions are already defined above) ─────────────────

    _s["configure"] = ConfigureScreen(page, on_run=_start_pipeline)
    _s["running"] = RunningScreen(page, on_cancel=_cancel_pipeline)
    _s["review"] = ReviewScreen(page, on_back=_show_configure)

    _show_configure()


if __name__ == "__main__":
    ft.run(main)
