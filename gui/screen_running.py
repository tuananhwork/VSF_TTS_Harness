"""Màn hình 2 — Running: stepper ngang + log output."""
from __future__ import annotations

import time
from typing import Callable

import flet as ft

import theme as T

_STEPS = ["scan", "judge", "synth"]
_STEP_LABELS = {"scan": "Scan", "judge": "Judge", "synth": "Synth"}

_BADGE = 34  # đường kính badge tròn


class RunningScreen:
    def __init__(self, page: ft.Page, on_cancel: Callable) -> None:
        self._page = page
        self._on_cancel = on_cancel
        self._log_lines: list[str] = []
        self._badges: dict[str, ft.Container] = {}
        self._labels: dict[str, ft.Text] = {}
        self._connectors: list[ft.Container] = []
        # Live "đang gọi LLM" bar (spinner + nhãn + đồng hồ elapsed).
        self._activity_label: str | None = None
        self._activity_start: float = 0.0

        # Clipboard service phải gắn vào page mới dùng được (Flet 0.85+).
        self._clipboard = ft.Clipboard()
        page.services.append(self._clipboard)

        self._build()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        stepper_items: list[ft.Control] = []
        for i, step in enumerate(_STEPS):
            badge, label = self._make_step(i)
            self._badges[step] = badge
            self._labels[step] = label
            stepper_items.append(
                ft.Column(
                    [badge, label],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=T.SM,
                )
            )
            if i < len(_STEPS) - 1:
                connector = ft.Container(
                    height=2,
                    bgcolor=T.HAIRLINE,
                    expand=True,
                    margin=ft.Margin(left=T.SM, top=0, right=T.SM,
                                     bottom=22),  # canh giữa hàng badge
                    border_radius=2,
                )
                self._connectors.append(connector)
                stepper_items.append(connector)

        stepper = ft.Row(
            stepper_items,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        # ── Log ──────────────────────────────────────────────────────────────
        self._log_view = ft.ListView(
            expand=True, spacing=2, auto_scroll=True, padding=T.pad_all(T.SM),
        )
        log_card = ft.Container(
            content=self._log_view,
            bgcolor=T.SURFACE_ALT,
            border=T.hairline(),
            border_radius=T.RADIUS_MD,
            expand=True,
        )

        # ── Buttons ────────────────────────────────────────────────────────────
        btn_row = ft.Row([
            ft.OutlinedButton(
                content=ft.Row([ft.Icon(ft.Icons.CLOSE, size=18), ft.Text("Huỷ")],
                               spacing=T.XS, tight=True),
                on_click=lambda e: self._on_cancel(),
            ),
            ft.Container(expand=True),
            ft.TextButton(
                content=ft.Row([ft.Icon(ft.Icons.CONTENT_COPY, size=18),
                                ft.Text("Copy log")], spacing=T.XS, tight=True),
                on_click=self._copy_log,
            ),
        ])

        # ── Live activity bar (ẩn khi không có call LLM đang chạy) ───────────
        self._activity_ring = ft.ProgressRing(width=16, height=16, stroke_width=2)
        self._activity_text = ft.Text(
            "", theme_style=ft.TextThemeStyle.BODY_SMALL, color=ft.Colors.PRIMARY,
            weight=ft.FontWeight.W_500,
        )
        self._activity_bar = ft.Container(
            content=ft.Row(
                [self._activity_ring, self._activity_text],
                spacing=T.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
            padding=T.pad_xy(T.MD, T.SM),
            bgcolor=T.SURFACE_ALT,
            border=T.hairline(),
            border_radius=T.RADIUS_SM,
        )

        self.container = ft.Container(
            content=ft.Column(
                [
                    T.screen_header("Đang chạy pipeline",
                                    "Quét log → chấm điểm → tổng hợp skill"),
                    T.gap(T.LG),
                    stepper,
                    T.gap(T.LG),
                    self._activity_bar,
                    T.gap(T.SM),
                    log_card,
                    T.gap(T.MD),
                    btn_row,
                ],
                expand=True,
                spacing=0,
            ),
            padding=T.pad_all(T.XL),
            expand=True,
        )

    def _make_step(self, i: int) -> tuple[ft.Container, ft.Text]:
        badge = ft.Container(
            width=_BADGE,
            height=_BADGE,
            border_radius=_BADGE // 2,
            alignment=ft.Alignment(0, 0),
            bgcolor=T.SURFACE_ALT,
            border=T.hairline(),
            content=ft.Text(str(i + 1), color=T.MUTED, weight=ft.FontWeight.BOLD),
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        )
        label = ft.Text(
            _STEP_LABELS[_STEPS[i]],
            theme_style=ft.TextThemeStyle.LABEL_MEDIUM,
            color=T.MUTED,
        )
        return badge, label

    # ── Public API ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._log_lines = []
        self._log_view.controls.clear()
        for i, step in enumerate(_STEPS):
            self._set_step("pending", step, i)
        for c in self._connectors:
            c.bgcolor = T.HAIRLINE
        self.clear_activity()

    # ── Live activity bar ─────────────────────────────────────────────────────

    def set_activity(self, label: str) -> None:
        """Hiện thanh live cho call LLM đang chạy + bắt đầu đếm elapsed."""
        self._activity_label = label
        self._activity_start = time.monotonic()
        self._activity_text.value = label
        self._activity_bar.visible = True

    def clear_activity(self) -> None:
        self._activity_label = None
        self._activity_bar.visible = False

    def tick_elapsed(self) -> bool:
        """Cập nhật giây trôi qua. Trả True khi nhãn đổi (≈mỗi 1s) để caller update."""
        if not self._activity_label:
            return False
        secs = int(time.monotonic() - self._activity_start)
        new = f"{self._activity_label}  ·  {secs}s"
        if self._activity_text.value != new:
            self._activity_text.value = new
            return True
        return False

    def update_step(self, status: str, step: str) -> None:
        self._set_step(status, step, _STEPS.index(step))
        if status == "done":
            idx = _STEPS.index(step)
            if idx < len(self._connectors):
                self._connectors[idx].bgcolor = ft.Colors.PRIMARY

    def append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self._log_view.controls.append(
            ft.Text(msg, size=12, font_family="Consolas", selectable=True,
                    color=ft.Colors.ON_SURFACE)
        )

    def append_error(self, msg: str) -> None:
        self._log_lines.append(f"✗ {msg}")
        self._log_view.controls.append(
            ft.Text(f"✗ {msg}", size=12, font_family="Consolas",
                    color=ft.Colors.ERROR, selectable=True)
        )

    # ── Private ──────────────────────────────────────────────────────────────

    def _set_step(self, status: str, step: str, i: int) -> None:
        badge = self._badges[step]
        label = self._labels[step]
        if status == "running":
            badge.bgcolor = ft.Colors.PRIMARY
            badge.border = None
            badge.content = ft.ProgressRing(
                width=16, height=16, stroke_width=2, color=ft.Colors.ON_PRIMARY,
            )
            label.color = ft.Colors.PRIMARY
            label.weight = ft.FontWeight.BOLD
        elif status == "done":
            badge.bgcolor = T.SUCCESS
            badge.border = None
            badge.content = ft.Icon(ft.Icons.CHECK_ROUNDED,
                                    color=ft.Colors.WHITE, size=20)
            label.color = ft.Colors.ON_SURFACE
            label.weight = ft.FontWeight.W_500
        elif status == "error":
            badge.bgcolor = ft.Colors.ERROR
            badge.border = None
            badge.content = ft.Icon(ft.Icons.CLOSE_ROUNDED,
                                    color=ft.Colors.WHITE, size=20)
            label.color = ft.Colors.ERROR
            label.weight = ft.FontWeight.BOLD
        else:  # pending
            badge.bgcolor = T.SURFACE_ALT
            badge.border = T.hairline()
            badge.content = ft.Text(str(i + 1), color=T.MUTED,
                                    weight=ft.FontWeight.BOLD)
            label.color = T.MUTED
            label.weight = ft.FontWeight.NORMAL

    def _copy_log(self, e) -> None:
        text = "\n".join(self._log_lines)
        self._page.run_task(self._clipboard.set, text)
        self._page.show_dialog(
            ft.SnackBar(content=ft.Text("Đã copy log vào clipboard"))
        )
