"""Màn hình 2 — Running: step status + log output."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

_STEPS = ["scan", "judge", "synth"]
_STEP_LABELS = {"scan": "Scan", "judge": "Judge", "synth": "Synth"}
_ICONS = {"pending": "○", "running": "⏳", "done": "✓", "error": "✗"}


class RunningScreen(ctk.CTkFrame):
    def __init__(self, master, on_cancel: Callable[[], None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_cancel = on_cancel
        self._step_labels: dict[str, ctk.CTkLabel] = {}
        self._log_lines: list[str] = []
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Đang chạy pipeline...",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=(24, 12), padx=24, sticky="w"
        )

        steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        steps_frame.grid(row=1, column=0, padx=24, sticky="ew")
        for i, step in enumerate(_STEPS):
            lbl = ctk.CTkLabel(steps_frame,
                               text=f"{_ICONS['pending']}  {_STEP_LABELS[step]}",
                               font=ctk.CTkFont(size=13))
            lbl.grid(row=i, column=0, pady=3, sticky="w")
            self._step_labels[step] = lbl

        self._log_box = ctk.CTkTextbox(self, height=220, state="disabled",
                                        font=ctk.CTkFont(family="Consolas", size=11))
        self._log_box.grid(row=2, column=0, padx=24, pady=(16, 0), sticky="nsew")
        self.grid_rowconfigure(2, weight=1)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=24, pady=16, sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_frame, text="Huỷ", width=80, fg_color="gray40",
                      command=self._on_cancel).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(btn_frame, text="Copy log 📋", width=100,
                      command=self._copy_log).grid(row=0, column=2, sticky="e")

    def reset(self) -> None:
        self._log_lines = []
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        for step in _STEPS:
            self._set_step("pending", step)

    def update_step(self, status: str, step: str) -> None:
        self._set_step(status, step)

    def append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def append_error(self, msg: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"ERROR: {msg}\n", "error")
        self._log_box.tag_config("error", foreground="red")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_step(self, status: str, step: str) -> None:
        icon = _ICONS.get(status, "○")
        color = {"done": "green", "error": "red", "running": "orange"}.get(status)
        lbl = self._step_labels[step]
        lbl.configure(text=f"{icon}  {_STEP_LABELS[step]}")
        if color:
            lbl.configure(text_color=color)

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append("\n".join(self._log_lines))
