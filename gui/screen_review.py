"""Màn hình 3 — Review & Accept: chọn skill để cài."""
from __future__ import annotations

from typing import Callable

import flet as ft

from pipeline_runner import SkillProposal, install_skill

_CONF = {
    "cao":        {"bg": "#2E7D32", "label": "Cao"},
    "trung bình": {"bg": "#E65100", "label": "TB"},
    "thấp":       {"bg": "#616161", "label": "Thấp"},
}
_ACCENT = {
    "cao":        "#4CAF50",
    "trung bình": "#FF8A65",
    "thấp":       "#9E9E9E",
}


class ReviewScreen:
    def __init__(self, page: ft.Page, on_back: Callable) -> None:
        self._page = page
        self._on_back = on_back
        self._proposals: list[SkillProposal] = []
        self._checkboxes: list[ft.Checkbox] = []
        self._build()

    def _build(self) -> None:
        self._header_lbl = ft.Text("", size=18, weight=ft.FontWeight.BOLD)

        self._select_all = ft.Checkbox(
            label="Chọn tất cả",
            value=True,
            on_change=self._on_select_all,
        )

        self._card_list = ft.ListView(expand=True, spacing=8)

        btn_row = ft.Row([
            ft.OutlinedButton("← Quay lại", on_click=lambda e: self._on_back()),
            ft.Container(expand=True),
            ft.FilledButton(
                "Cài các skill đã chọn",
                on_click=self._install_selected,
            ),
        ])

        self.container = ft.Container(
            content=ft.Column([
                self._header_lbl,
                ft.Text("Chọn skill muốn cài vào Claude:", size=12, color="#757575"),
                ft.Container(height=4),
                self._select_all,
                ft.Divider(height=1, color="#E0E0E0"),
                ft.Container(height=4),
                self._card_list,
                ft.Container(height=8),
                btn_row,
            ], expand=True, spacing=4),
            padding=ft.Padding(left=28, right=28, top=24, bottom=24),
            expand=True,
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def load_proposals(self, proposals: list[SkillProposal]) -> None:
        self._proposals = proposals
        self._checkboxes = []
        self._card_list.controls.clear()
        self._select_all.value = True

        n = len(proposals)
        self._header_lbl.value = (
            f"Phát hiện {n} pattern mới" if n != 1 else "Phát hiện 1 pattern mới"
        )

        for p in proposals:
            cb = ft.Checkbox(value=True)
            self._checkboxes.append(cb)
            self._card_list.controls.append(self._build_card(p, cb))

    # ── Card builder ─────────────────────────────────────────────────────────

    def _build_card(self, p: SkillProposal, cb: ft.Checkbox) -> ft.Control:
        conf_style = _CONF.get(p.confidence, _CONF["thấp"])
        accent = _ACCENT.get(p.confidence, "#9E9E9E")

        badge = ft.Container(
            content=ft.Text(
                conf_style["label"],
                size=10,
                weight=ft.FontWeight.BOLD,
                color="white",
            ),
            bgcolor=conf_style["bg"],
            border_radius=4,
            padding=ft.Padding(left=7, right=7, top=3, bottom=3),
        )

        meta_items: list[ft.Control] = [
            ft.Text(f"Lặp {p.recurrence} lần", size=11, color="#9E9E9E"),
            badge,
        ]
        if p.has_quality_issues:
            meta_items.append(ft.Text("⚠ Cần review", size=10, color="#E65100"))

        desc = p.description[:90] + "…" if len(p.description) > 90 else p.description

        return ft.Container(
            content=ft.Row([
                # Left accent strip
                ft.Container(
                    width=4,
                    bgcolor=accent,
                    border_radius=ft.BorderRadius(top_left=8, top_right=0, bottom_left=8, bottom_right=0),
                ),
                # Checkbox
                ft.Container(content=cb, padding=ft.Padding(left=10, right=10, top=0, bottom=0)),
                # Text content
                ft.Column([
                    ft.Text(p.name, size=13, weight=ft.FontWeight.BOLD),
                    ft.Text(desc, size=11, color="#757575", max_lines=2),
                    ft.Row(meta_items, spacing=6),
                ], expand=True, spacing=4),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            border=ft.Border(top=ft.BorderSide(1,"#E0E0E0"), right=ft.BorderSide(1,"#E0E0E0"), bottom=ft.BorderSide(1,"#E0E0E0"), left=ft.BorderSide(1,"#E0E0E0")),
            border_radius=8,
            padding=ft.Padding(left=0, right=14, top=10, bottom=10),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
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
        elif failed:
            msg = "Không cài được skill nào.\n" + "\n".join(failed)
        else:
            msg = "Không có skill nào được chọn."

        self._show_dialog("Pattern — Hoàn tất", msg)

    def _show_dialog(self, title: str, content: str) -> None:
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(content),
        )

        def close(e):
            dlg.open = False
            self._page.overlay.remove(dlg)
            self._page.update()

        dlg.actions = [ft.TextButton("OK", on_click=close)]
        self._page.overlay.append(dlg)
        dlg.open = True
        self._page.update()
