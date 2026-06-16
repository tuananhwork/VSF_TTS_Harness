"""Màn hình 2 — Running: horizontal stepper + log output."""
from __future__ import annotations

from typing import Callable

import flet as ft

_STEPS = ["scan", "judge", "synth"]
_STEP_LABELS = {"scan": "Scan", "judge": "Judge", "synth": "Synth"}

_STATUS: dict[str, dict[str, str]] = {
    "pending": {"icon": "○", "color": "#9E9E9E"},
    "running": {"icon": "●", "color": "#1E88E5"},
    "done":    {"icon": "✓", "color": "#2E7D32"},
    "error":   {"icon": "✗", "color": "#C62828"},
}
_LINE_INACTIVE = "#BDBDBD"
_LINE_ACTIVE = "#1E88E5"


class RunningScreen:
    def __init__(self, page: ft.Page, on_cancel: Callable) -> None:
        self._page = page
        self._on_cancel = on_cancel
        self._log_lines: list[str] = []
        self._step_icons: dict[str, ft.Text] = {}
        self._step_name_lbls: dict[str, ft.Text] = {}
        self._connector_lines: list[ft.Container] = []
        self._build()

    def _build(self) -> None:
        # ── Stepper: icon row + label row ────────────────────────────────────
        icon_items: list[ft.Control] = []
        label_items: list[ft.Control] = []

        for i, step in enumerate(_STEPS):
            icon = ft.Text(
                _STATUS["pending"]["icon"],
                size=24,
                color=_STATUS["pending"]["color"],
                text_align=ft.TextAlign.CENTER,
            )
            name = ft.Text(
                _STEP_LABELS[step],
                size=11,
                color=_STATUS["pending"]["color"],
                text_align=ft.TextAlign.CENTER,
            )
            self._step_icons[step] = icon
            self._step_name_lbls[step] = name

            icon_items.append(
                ft.Container(content=icon, width=72, alignment=ft.Alignment(0, 0))
            )
            label_items.append(
                ft.Container(content=name, width=72, alignment=ft.Alignment(0, 0))
            )

            if i < len(_STEPS) - 1:
                connector = ft.Container(
                    height=2, bgcolor=_LINE_INACTIVE, expand=True,
                )
                self._connector_lines.append(connector)
                icon_items.append(connector)
                label_items.append(ft.Container(expand=True))

        stepper = ft.Column([
            ft.Row(icon_items, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(label_items),
        ], spacing=4)

        # ── Log list ─────────────────────────────────────────────────────────
        self._log_view = ft.ListView(
            expand=True,
            spacing=1,
            auto_scroll=True,
            padding=ft.Padding(left=4, right=4, top=4, bottom=4),
        )

        log_container = ft.Container(
            content=self._log_view,
            border=ft.Border(top=ft.BorderSide(1,"#E0E0E0"), right=ft.BorderSide(1,"#E0E0E0"), bottom=ft.BorderSide(1,"#E0E0E0"), left=ft.BorderSide(1,"#E0E0E0")),
            border_radius=8,
            expand=True,
        )

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_row = ft.Row([
            ft.OutlinedButton("Huỷ", on_click=lambda e: self._on_cancel()),
            ft.Container(expand=True),
            ft.OutlinedButton("Copy log", on_click=self._copy_log),
        ])

        # ── Container ─────────────────────────────────────────────────────────
        self.container = ft.Container(
            content=ft.Column([
                ft.Text("Đang chạy pipeline…", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(height=16),
                stepper,
                ft.Container(height=16),
                log_container,
                ft.Container(height=12),
                btn_row,
            ], expand=True, spacing=0),
            padding=ft.Padding(left=28, right=28, top=28, bottom=28),
            expand=True,
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._log_lines = []
        self._log_view.controls.clear()
        for step in _STEPS:
            self._set_step("pending", step)
        for line in self._connector_lines:
            line.bgcolor = _LINE_INACTIVE

    def update_step(self, status: str, step: str) -> None:
        self._set_step(status, step)
        if status == "done":
            idx = _STEPS.index(step)
            if idx < len(self._connector_lines):
                self._connector_lines[idx].bgcolor = _LINE_ACTIVE

    def append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self._log_view.controls.append(
            ft.Text(msg, size=11, font_family="Consolas", selectable=True)
        )

    def append_error(self, msg: str) -> None:
        self._log_view.controls.append(
            ft.Text(
                f"✗ {msg}",
                size=11,
                font_family="Consolas",
                color="#EF5350",
                selectable=True,
            )
        )

    # ── Private ──────────────────────────────────────────────────────────────

    def _set_step(self, status: str, step: str) -> None:
        s = _STATUS.get(status, _STATUS["pending"])
        self._step_icons[step].value = s["icon"]
        self._step_icons[step].color = s["color"]
        self._step_name_lbls[step].color = s["color"]

    def _copy_log(self, e) -> None:
        self._page.clipboard = "\n".join(self._log_lines)
