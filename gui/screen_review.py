"""Màn hình 3 — Review & Accept: chọn skill để cài."""
from __future__ import annotations

import sys
import tkinter.messagebox as mb
from pathlib import Path
from typing import Callable

import customtkinter as ctk

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from pipeline_runner import SkillProposal, install_skill

_CONFIDENCE_COLOR = {
    "cao": "green",
    "trung bình": "orange",
    "thấp": "gray",
}


class ReviewScreen(ctk.CTkFrame):
    def __init__(self, master, on_back: Callable[[], None], **kwargs):
        super().__init__(master, **kwargs)
        self._on_back = on_back
        self._proposals: list[SkillProposal] = []
        self._checkboxes: list[ctk.BooleanVar] = []
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._header = ctk.CTkLabel(self, text="",
                                     font=ctk.CTkFont(size=16, weight="bold"))
        self._header.grid(row=0, column=0, pady=(24, 8), padx=24, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.grid(row=1, column=0, padx=24, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=24, pady=16, sticky="ew")
        btn_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_frame, text="← Quay lại", width=100,
                      fg_color="gray40", command=self._on_back).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(btn_frame, text="Cài skill đã chọn", height=36,
                      command=self._install_selected).grid(row=0, column=2, sticky="e")

    def load_proposals(self, proposals: list[SkillProposal]) -> None:
        self._proposals = proposals
        self._checkboxes = []

        for w in self._scroll.winfo_children():
            w.destroy()

        self._header.configure(text=f"Phát hiện {len(proposals)} skill. Chọn để cài:")

        for i, p in enumerate(proposals):
            var = ctk.BooleanVar(value=True)
            self._checkboxes.append(var)
            self._build_card(i, p, var)

    def _build_card(self, idx: int, p: SkillProposal, var: ctk.BooleanVar) -> None:
        card = ctk.CTkFrame(self._scroll, border_width=1)
        card.grid(row=idx, column=0, pady=4, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkCheckBox(card, text="", variable=var, width=24).grid(
            row=0, column=0, rowspan=2, padx=(12, 0), pady=8
        )
        ctk.CTkLabel(card, text=p.name,
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, padx=8, pady=(8, 0), sticky="w"
        )

        desc = p.description[:80] + "..." if len(p.description) > 80 else p.description
        ctk.CTkLabel(card, text=desc,
                     text_color=("gray40", "gray60")).grid(
            row=1, column=1, padx=8, sticky="w"
        )

        meta = f"Lặp {p.recurrence} lần  •  Độ tin cậy: {p.confidence}"
        if p.has_quality_issues:
            meta += "  ⚠"
        ctk.CTkLabel(card, text=meta,
                     text_color=_CONFIDENCE_COLOR.get(p.confidence, "gray"),
                     font=ctk.CTkFont(size=11)).grid(
            row=2, column=1, padx=8, pady=(0, 8), sticky="w"
        )

    def _install_selected(self) -> None:
        installed = []
        for proposal, var in zip(self._proposals, self._checkboxes):
            if var.get():
                try:
                    install_skill(proposal)
                    installed.append(proposal.name)
                except Exception:
                    pass

        msg = (
            f"Đã cài {len(installed)} skill: {', '.join(installed)}.\n"
            "Có hiệu lực phiên Claude tiếp theo."
            if installed
            else "Không có skill nào được chọn."
        )
        mb.showinfo("Pattern", msg)
