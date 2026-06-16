"""Màn hình 1 — Configure: chọn ngày, source, tùy chọn nâng cao."""
from __future__ import annotations

from datetime import date
from typing import Callable

import customtkinter as ctk
from tkcalendar import DateEntry


class ConfigureScreen(ctk.CTkFrame):
    def __init__(self, master, on_run: Callable[..., None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_run = on_run
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Pattern", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, pady=(24, 4), padx=24, sticky="w"
        )
        ctk.CTkLabel(self, text="Phân tích hành vi Claude → gợi ý Skill").grid(
            row=1, column=0, padx=24, sticky="w"
        )

        ctk.CTkLabel(self, text="Ngày phân tích", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=24, pady=(20, 4), sticky="w"
        )
        self._date_entry = DateEntry(
            self,
            width=16,
            date_pattern="yyyy-mm-dd",
            year=date.today().year,
            month=date.today().month,
            day=date.today().day,
        )
        self._date_entry.grid(row=3, column=0, padx=24, sticky="w")

        ctk.CTkLabel(self, text="Nguồn log", font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, padx=24, pady=(16, 4), sticky="w"
        )
        self._source_var = ctk.StringVar(value="claude-cowork")
        source_frame = ctk.CTkFrame(self, fg_color="transparent")
        source_frame.grid(row=5, column=0, padx=24, sticky="w")
        ctk.CTkRadioButton(source_frame, text="claude-cowork (Desktop)", variable=self._source_var,
                           value="claude-cowork").pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(source_frame, text="claude-code (CLI)", variable=self._source_var,
                           value="claude-code").pack(side="left")

        self._adv_open = ctk.BooleanVar(value=False)
        adv_toggle = ctk.CTkButton(
            self, text="▶ Tùy chọn nâng cao", anchor="w",
            fg_color="transparent", text_color=("gray30", "gray70"),
            hover=False, command=self._toggle_advanced,
        )
        adv_toggle.grid(row=6, column=0, padx=20, pady=(16, 0), sticky="w")
        self._adv_toggle_btn = adv_toggle

        self._adv_frame = ctk.CTkFrame(self)
        self._adv_frame.grid(row=7, column=0, padx=24, pady=(4, 0), sticky="ew")
        self._adv_frame.grid_remove()

        ctk.CTkLabel(self._adv_frame, text="Min recurrence").grid(row=0, column=0, padx=8, pady=4, sticky="w")
        self._min_rec = ctk.CTkEntry(self._adv_frame, width=60)
        self._min_rec.insert(0, "2")
        self._min_rec.grid(row=0, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="Max deepdive").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        self._max_dd = ctk.CTkEntry(self._adv_frame, width=60)
        self._max_dd.insert(0, "5")
        self._max_dd.grid(row=1, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="LLM provider").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        self._provider_var = ctk.StringVar(value="claude")
        ctk.CTkOptionMenu(self._adv_frame, values=["claude", "ccs"],
                          variable=self._provider_var).grid(row=2, column=1, padx=8)

        ctk.CTkLabel(self._adv_frame, text="CCS profile").grid(row=3, column=0, padx=8, pady=4, sticky="w")
        self._ccs_entry = ctk.CTkEntry(self._adv_frame, width=120, placeholder_text="tên profile")
        self._ccs_entry.grid(row=3, column=1, padx=8)

        ctk.CTkButton(self, text="Chạy Pipeline", height=40,
                      command=self._on_run_click).grid(
            row=8, column=0, padx=24, pady=24, sticky="ew"
        )

    def _toggle_advanced(self) -> None:
        if self._adv_open.get():
            self._adv_frame.grid_remove()
            self._adv_toggle_btn.configure(text="▶ Tùy chọn nâng cao")
            self._adv_open.set(False)
        else:
            self._adv_frame.grid()
            self._adv_toggle_btn.configure(text="▼ Tùy chọn nâng cao")
            self._adv_open.set(True)

    def _on_run_click(self) -> None:
        try:
            min_rec = int(self._min_rec.get())
            max_dd = int(self._max_dd.get())
        except ValueError:
            min_rec, max_dd = 2, 5

        self._on_run(
            date=self._date_entry.get_date().isoformat(),
            source=self._source_var.get(),
            min_recurrence=min_rec,
            max_deepdive=max_dd,
        )
