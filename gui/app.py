"""Pattern GUI — main app entry point."""
from __future__ import annotations

import queue
import sys
from pathlib import Path

import customtkinter as ctk

_GUI = Path(__file__).resolve().parent
if str(_GUI) not in sys.path:
    sys.path.insert(0, str(_GUI))

from pipeline_runner import PipelineParams, PipelineRunner, SkillProposal
from screen_configure import ConfigureScreen
from screen_running import RunningScreen
from screen_review import ReviewScreen

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

_POLL_MS = 50


class PatternApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pattern")
        self.geometry("500x560")
        self.resizable(False, False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._q: queue.Queue = queue.Queue()
        self._runner: PipelineRunner | None = None

        self._configure = ConfigureScreen(self, on_run=self._start_pipeline)
        self._running = RunningScreen(self, on_cancel=self._cancel_pipeline)
        self._review = ReviewScreen(self, on_back=self._show_configure)

        self._show_configure()

    def _show_configure(self) -> None:
        self._running.grid_remove()
        self._review.grid_remove()
        self._configure.grid(row=0, column=0, sticky="nsew")

    def _show_running(self) -> None:
        self._configure.grid_remove()
        self._review.grid_remove()
        self._running.grid(row=0, column=0, sticky="nsew")

    def _show_review(self, proposals: list[SkillProposal]) -> None:
        self._running.grid_remove()
        self._configure.grid_remove()
        self._review.load_proposals(proposals)
        self._review.grid(row=0, column=0, sticky="nsew")

    def _start_pipeline(self, date: str, source: str,
                        min_recurrence: int, max_deepdive: int) -> None:
        params = PipelineParams(
            date=date,
            source=source,
            min_recurrence=min_recurrence,
            max_deepdive=max_deepdive,
        )
        self._running.reset()
        self._show_running()
        self._runner = PipelineRunner(params, self._q)
        self._runner.start()
        self.after(_POLL_MS, self._poll_queue)

    def _cancel_pipeline(self) -> None:
        if self._runner:
            self._runner.cancel()
        self._show_configure()

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass

        if self._runner and self._runner.is_alive():
            self.after(_POLL_MS, self._poll_queue)

    def _handle_msg(self, msg: tuple) -> None:
        kind = msg[0]

        if kind == "log":
            self._running.append_log(msg[1])
        elif kind == "step_start":
            self._running.update_step("running", msg[1])
        elif kind == "step_done":
            self._running.update_step("done", msg[1])
        elif kind == "step_error":
            step, err = msg[1], msg[2]
            self._running.update_step("error", step)
            self._running.append_error(err)
        elif kind == "no_sessions":
            self._running.append_log("Không có session nào cho ngày này. Thử ngày khác.")
        elif kind == "no_candidates":
            self._running.append_log("Chưa phát hiện pattern đủ mạnh. Thử quét nhiều ngày hơn.")
        elif kind == "done":
            self._show_review(msg[1])


def main() -> None:
    app = PatternApp()
    app.mainloop()


if __name__ == "__main__":
    main()
