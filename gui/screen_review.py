"""Màn hình 3 — Review & Accept: chọn skill để cài."""
from __future__ import annotations

from typing import Callable

import flet as ft

import theme as T
from pipeline_runner import SkillProposal, install_skill


class ReviewScreen:
    def __init__(self, page: ft.Page, on_back: Callable) -> None:
        self._page = page
        self._on_back = on_back
        self._proposals: list[SkillProposal] = []
        self._checkboxes: list[ft.Checkbox] = []
        self._build()

    def _build(self) -> None:
        self._header = T.screen_header(
            "Kết quả",
            "Chọn skill muốn cài vào Claude",
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK_ROUNDED,
                tooltip="Quay lại",
                on_click=lambda e: self._on_back(),
            ),
        )

        self._select_all = ft.Checkbox(
            label="Chọn tất cả", value=True, on_change=self._on_select_all,
        )
        self._count_lbl = ft.Text("", theme_style=ft.TextThemeStyle.BODY_SMALL,
                                  color=T.MUTED)

        self._card_list = ft.ListView(expand=True, spacing=T.SM)

        self._install_btn = ft.FilledButton(
            content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=18),
                            ft.Text("Cài skill đã chọn", weight=ft.FontWeight.W_600)],
                           spacing=T.XS, tight=True),
            on_click=self._install_selected,
            height=48,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD)),
        )

        self.container = ft.Container(
            content=ft.Column(
                [
                    self._header,
                    T.gap(T.MD),
                    ft.Row([self._select_all, ft.Container(expand=True),
                            self._count_lbl],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Divider(height=1, color=T.HAIRLINE),
                    T.gap(T.SM),
                    self._card_list,
                    T.gap(T.MD),
                    ft.Row([ft.Container(expand=True), self._install_btn]),
                ],
                expand=True,
                spacing=0,
            ),
            padding=T.pad_all(T.XL),
            expand=True,
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def load_proposals(self, proposals: list[SkillProposal]) -> None:
        self._proposals = proposals
        self._checkboxes = []
        self._card_list.controls.clear()
        self._select_all.value = True

        self._count_lbl.value = f"{len(proposals)} pattern"

        for p in proposals:
            cb = ft.Checkbox(value=True)
            self._checkboxes.append(cb)
            self._card_list.controls.append(self._build_card(p, cb))

    # ── Card builder ─────────────────────────────────────────────────────────

    def _build_card(self, p: SkillProposal, cb: ft.Checkbox) -> ft.Control:
        conf = T.CONFIDENCE.get(p.confidence, T.CONFIDENCE["thấp"])
        accent = conf["color"]

        badge = ft.Container(
            content=ft.Text(conf["label"], size=11, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE),
            bgcolor=accent,
            border_radius=T.RADIUS_SM,
            padding=T.pad_xy(8, 3),
        )

        meta_items: list[ft.Control] = [
            ft.Row([ft.Icon(ft.Icons.REPLAY_ROUNDED, size=14, color=T.MUTED),
                    ft.Text(f"Lặp {p.recurrence} lần", size=12, color=T.MUTED)],
                   spacing=T.XS, tight=True),
            badge,
        ]
        if p.has_quality_issues:
            meta_items.append(
                ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=14,
                                color=T.WARNING),
                        ft.Text("Cần review", size=11, color=T.WARNING)],
                       spacing=T.XS, tight=True)
            )

        desc = p.description[:110] + "…" if len(p.description) > 110 else p.description

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=4, bgcolor=accent, border_radius=2,
                                 margin=ft.Margin(left=0, top=2, right=T.SM,
                                                  bottom=2)),
                    cb,
                    ft.Column(
                        [
                            ft.Text(p.name, theme_style=ft.TextThemeStyle.TITLE_SMALL,
                                    weight=ft.FontWeight.BOLD),
                            ft.Text(desc, theme_style=ft.TextThemeStyle.BODY_SMALL,
                                    color=T.MUTED, max_lines=2),
                            ft.Container(height=2),
                            ft.Row(meta_items, spacing=T.SM, wrap=True),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=T.SM,
            ),
            bgcolor=T.SURFACE_ALT,
            border=T.hairline(),
            border_radius=T.RADIUS_MD,
            padding=T.pad(left=T.SM, top=T.MD, right=T.MD, bottom=T.MD),
        )

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _on_select_all(self, e) -> None:
        for cb in self._checkboxes:
            cb.value = e.control.value
        self._page.update()

    def _install_selected(self, e) -> None:
        installed, failed = [], []
        for proposal, cb in zip(self._proposals, self._checkboxes):
            if cb.value:
                try:
                    install_skill(proposal)
                    installed.append(proposal.name)
                except Exception as exc:
                    failed.append(f"{proposal.name} ({exc})")

        if installed:
            msg = f"Đã cài {len(installed)} skill:\n• " + "\n• ".join(installed)
            if failed:
                msg += f"\n\nLỗi ({len(failed)}):\n• " + "\n• ".join(failed)
            msg += "\n\nCó hiệu lực từ phiên Claude tiếp theo."
            icon, tint = ft.Icons.CHECK_CIRCLE_ROUNDED, T.SUCCESS
        elif failed:
            msg = "Không cài được skill nào.\n• " + "\n• ".join(failed)
            icon, tint = ft.Icons.ERROR_ROUNDED, ft.Colors.ERROR
        else:
            msg = "Bạn chưa chọn skill nào."
            icon, tint = ft.Icons.INFO_ROUNDED, T.MUTED

        self._show_result("Hoàn tất", msg, icon, tint)

    def _show_result(self, title: str, content: str, icon: str, tint: str) -> None:
        dlg = ft.AlertDialog(
            modal=True,
            icon=ft.Icon(icon, color=tint, size=32),
            title=ft.Text(title, text_align=ft.TextAlign.CENTER),
            content=ft.Text(content),
            actions=[ft.FilledButton("OK", on_click=lambda e: self._page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dlg)
