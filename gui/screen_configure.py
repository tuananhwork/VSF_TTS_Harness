"""Màn hình 1 — Configure: chọn ngày, source, tùy chọn nâng cao."""
from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Callable

import flet as ft

_SOURCES = ["claude-cowork", "claude-code"]


class ConfigureScreen:
    def __init__(self, page: ft.Page, on_run: Callable) -> None:
        self._page = page
        self._on_run = on_run
        self._selected_date: date = date.today()
        self._source: str = _SOURCES[0]
        self._build()

    def _build(self) -> None:
        # ── Date picker (overlay dialog) ─────────────────────────────────────
        self._date_picker = ft.DatePicker(
            current_date=datetime.today(),
            on_change=self._on_date_change,
            first_date=datetime(2020, 1, 1),
            last_date=datetime(2030, 12, 31),
        )
        self._page.overlay.append(self._date_picker)

        # Positional text — Flet 0.85 buttons don't accept text= as keyword
        self._date_btn = ft.OutlinedButton(
            self._selected_date.isoformat(),
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=self._open_date_picker,
        )

        # ── Source segmented button ──────────────────────────────────────────
        self._source_seg = ft.SegmentedButton(
            selected=[_SOURCES[0]],
            segments=[ft.Segment(value=s, label=s) for s in _SOURCES],
            on_change=self._on_source_change,
        )

        # ── Advanced options ─────────────────────────────────────────────────
        self._min_rec = ft.TextField(
            value="2",
            width=72,
            height=40,
            dense=True,
            text_align=ft.TextAlign.CENTER,
            border_radius=6,
        )
        self._max_dd = ft.TextField(
            value="5",
            width=72,
            height=40,
            dense=True,
            text_align=ft.TextAlign.CENTER,
            border_radius=6,
        )

        adv_tile = ft.ExpansionTile(
            title=ft.Text("Tùy chọn nâng cao", size=13, color="#9E9E9E"),
            controls=[
                ft.Column([
                    ft.Row([
                        ft.Text("Min recurrence", size=12, color="#757575", expand=True),
                        self._min_rec,
                    ]),
                    ft.Row([
                        ft.Text("Max deepdive", size=12, color="#757575", expand=True),
                        self._max_dd,
                    ]),
                ], spacing=8),
            ],
        )

        # ── Run button ───────────────────────────────────────────────────────
        run_btn = ft.Row([
            ft.FilledButton(
                "Chạy Pipeline",
                on_click=self._on_run_click,
                height=50,
                expand=True,
            ),
        ])

        # ── Container ────────────────────────────────────────────────────────
        self.container = ft.Container(
            content=ft.Column([
                ft.Text("Pattern", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Phân tích hành vi làm việc với Claude  →  gợi ý Skill",
                    size=12,
                    color="#757575",
                ),
                ft.Divider(height=1, color="#E0E0E0"),
                ft.Container(height=8),

                ft.Text("Ngày phân tích", size=13, weight=ft.FontWeight.BOLD),
                ft.Container(height=4),
                self._date_btn,
                ft.Container(height=20),

                ft.Text("Nguồn log", size=13, weight=ft.FontWeight.BOLD),
                ft.Container(height=4),
                self._source_seg,
                ft.Container(height=12),

                adv_tile,
                ft.Container(height=24),

                run_btn,
            ], spacing=0),
            padding=ft.Padding(left=28, right=28, top=28, bottom=28),
            expand=True,
        )

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _open_date_picker(self, e) -> None:
        self._date_picker.open = True
        self._page.update()

    def _on_date_change(self, e) -> None:
        if e.control.value:
            v = e.control.value
            # Flet returns UTC midnight as a naive datetime; convert to local to get correct date
            local_dt = v.replace(tzinfo=timezone.utc).astimezone(tz=None)
            self._selected_date = date(local_dt.year, local_dt.month, local_dt.day)
            self._date_btn.content = self._selected_date.isoformat()
            self._page.update()

    def _on_source_change(self, e) -> None:
        selected = e.control.selected
        if selected:
            self._source = list(selected)[0]

    def _on_run_click(self, e) -> None:
        try:
            min_rec = int(self._min_rec.value or "2")
            max_dd = int(self._max_dd.value or "5")
        except ValueError:
            min_rec, max_dd = 2, 5

        self._on_run(
            date=self._selected_date.isoformat(),
            source=self._source,
            min_recurrence=min_rec,
            max_deepdive=max_dd,
        )
