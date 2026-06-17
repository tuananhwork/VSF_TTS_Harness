"""Màn hình 1 — Configure: chọn ngày, nguồn log, tùy chọn nâng cao."""
from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Callable

import flet as ft

import theme as T

# (value, nhãn hiển thị, icon)
_SOURCES = [
    ("claude-cowork", "Cowork", ft.Icons.GROUPS_OUTLINED),
    ("claude-code", "Code", ft.Icons.TERMINAL),
]

# TODO(claude-code): tạm DISABLE nguồn "Code". Lý do: prompt triage cho claude-code
# quá lớn (vd ~264K ký tự với ~200 sessions) → vượt giới hạn command-line Windows
# (~32767 ký tự) khi prompt được truyền làm argv, khiến subprocess fail và bị báo
# nhầm là "claude CLI not found". Cần tối ưu trước khi bật lại:
#   (1) truyền prompt qua STDIN thay vì argv (claude -p và ccs đều đọc stdin), và
#   (2) chia batch sessions/clusters cho judge để prompt không phình.
# Khi đã làm xong, bỏ "claude-code" khỏi _DISABLED_SOURCES.
_DISABLED_SOURCES = {"claude-code"}
_DISABLED_TOOLTIP = "Tính năng đang phát triển"

# LLM provider chạy judge/synth. (value, nhãn, icon)
_PROVIDERS = [
    ("claude", "Claude", ft.Icons.AUTO_AWESOME),
    ("ccs", "CCS", ft.Icons.HUB_OUTLINED),
]


class ConfigureScreen:
    def __init__(self, page: ft.Page, on_run: Callable) -> None:
        self._page = page
        self._on_run = on_run
        self._selected_date: date = date.today()
        self._source: str = _SOURCES[0][0]
        self._provider: str = _PROVIDERS[0][0]
        self._build()

    def _build(self) -> None:
        # ── Date picker (mở qua page.show_dialog) ────────────────────────────
        self._date_picker = ft.DatePicker(
            current_date=datetime.today(),
            on_change=self._on_date_change,
            first_date=datetime(2020, 1, 1),
            last_date=datetime(2030, 12, 31),
        )

        self._date_text = ft.Text(
            self._selected_date.isoformat(),
            theme_style=ft.TextThemeStyle.BODY_LARGE,
            weight=ft.FontWeight.W_500,
            expand=True,
        )
        date_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CALENDAR_MONTH_OUTLINED, color=ft.Colors.PRIMARY),
                    self._date_text,
                    ft.Icon(ft.Icons.EXPAND_MORE, color=T.MUTED, size=20),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=T.MD,
            ),
            on_click=self._open_date_picker,
            bgcolor=T.SURFACE_ALT,
            border=T.hairline(),
            border_radius=T.RADIUS_MD,
            padding=T.pad_xy(T.MD, T.SM + 4),
            ink=True,
        )

        # ── Source segmented button ──────────────────────────────────────────
        # "Code" bị disable tạm (xem TODO ở đầu file); hover hiện tooltip.
        self._source_seg = ft.SegmentedButton(
            selected=[_SOURCES[0][0]],
            show_selected_icon=True,
            segments=[
                ft.Segment(
                    value=v,
                    label=ft.Text(lbl),
                    icon=ft.Icon(ic),
                    disabled=v in _DISABLED_SOURCES,
                    tooltip=_DISABLED_TOOLTIP if v in _DISABLED_SOURCES else None,
                )
                for v, lbl, ic in _SOURCES
            ],
            on_change=self._on_source_change,
        )

        # ── LLM Provider ──────────────────────────────────────────────────────
        self._provider_seg = ft.SegmentedButton(
            selected=[_PROVIDERS[0][0]],
            show_selected_icon=True,
            segments=[
                ft.Segment(value=v, label=ft.Text(lbl), icon=ft.Icon(ic))
                for v, lbl, ic in _PROVIDERS
            ],
            on_change=self._on_provider_change,
        )
        self._ccs_profile = ft.TextField(
            label="CCS profile (NAME)",
            hint_text="vd: one",
            dense=True,
            filled=True,
            border_radius=T.RADIUS_SM,
            prefix_icon=ft.Icons.BADGE_OUTLINED,
        )
        # Chỉ hiện ô profile khi provider = CCS.
        self._ccs_profile_box = ft.Container(
            content=self._ccs_profile,
            visible=False,
            padding=T.pad(top=T.SM),
        )

        # ── Tùy chọn nâng cao ─────────────────────────────────────────────────
        self._min_rec = self._num_field("2")
        self._max_dd = self._num_field("5")

        adv_tile = ft.ExpansionTile(
            title=ft.Text("Tùy chọn nâng cao",
                          theme_style=ft.TextThemeStyle.BODY_MEDIUM),
            leading=ft.Icon(ft.Icons.TUNE, size=20, color=T.MUTED),
            affinity=ft.TileAffinity.PLATFORM,
            controls=[
                ft.Container(
                    content=ft.Column([
                        self._adv_row(
                            "Số lần lặp tối thiểu",
                            "Pattern phải xuất hiện ít nhất bấy nhiêu lần",
                            self._min_rec,
                        ),
                        self._adv_row(
                            "Số deepdive tối đa",
                            "Giới hạn số pattern được phân tích sâu",
                            self._max_dd,
                        ),
                    ], spacing=T.MD),
                    padding=T.pad(left=T.SM, top=T.SM, right=T.SM, bottom=T.MD),
                ),
            ],
        )

        # ── Run button ────────────────────────────────────────────────────────
        run_btn = ft.FilledButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED),
                 ft.Text("Chạy Pipeline", weight=ft.FontWeight.W_600)],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=T.SM,
            ),
            on_click=self._on_run_click,
            height=52,
            expand=True,  # full-width khi đặt trong Row
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=T.RADIUS_MD),
            ),
        )

        # ── Layout ──────────────────────────────────────────────────────────
        self._theme_btn = ft.IconButton(
            icon=ft.Icons.DARK_MODE_OUTLINED,
            tooltip="Đổi giao diện sáng / tối",
            on_click=self._toggle_theme,
        )

        body = ft.Column(
            [
                T.screen_header(
                    "Pattern",
                    "Phân tích hành vi làm việc với Claude → gợi ý Skill",
                    trailing=self._theme_btn,
                ),
                T.gap(T.LG),

                T.section_label("Ngày phân tích"),
                T.gap(T.SM),
                date_card,
                T.gap(T.LG),

                T.section_label("Nguồn log"),
                T.gap(T.SM),
                self._source_seg,
                T.gap(T.LG),

                T.section_label("LLM Provider"),
                T.gap(T.SM),
                self._provider_seg,
                self._ccs_profile_box,
                T.gap(T.MD),

                adv_tile,
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.container = ft.Container(
            content=ft.Column(
                [
                    ft.Container(content=body, expand=True),
                    T.gap(T.MD),
                    ft.Row([run_btn]),
                ],
                spacing=0,
                expand=True,
            ),
            padding=T.pad_all(T.XL),
            expand=True,
        )

    # ── Builders nhỏ ──────────────────────────────────────────────────────────

    def _num_field(self, value: str) -> ft.TextField:
        return ft.TextField(
            value=value,
            width=80,
            height=44,
            dense=True,
            filled=True,
            text_align=ft.TextAlign.CENTER,
            border_radius=T.RADIUS_SM,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

    def _adv_row(self, title: str, hint: str, field: ft.TextField) -> ft.Control:
        return ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(title, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
                        ft.Text(hint, theme_style=ft.TextThemeStyle.BODY_SMALL,
                                color=T.MUTED),
                    ],
                    spacing=2,
                    expand=True,
                ),
                field,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _open_date_picker(self, e) -> None:
        self._page.show_dialog(self._date_picker)

    def _on_date_change(self, e) -> None:
        v = e.control.value
        if v:
            # Flet trả UTC midnight (naive); đổi sang local để lấy đúng ngày.
            local_dt = v.replace(tzinfo=timezone.utc).astimezone(tz=None)
            self._selected_date = date(local_dt.year, local_dt.month, local_dt.day)
            self._date_text.value = self._selected_date.isoformat()
            self._page.update()

    def _on_source_change(self, e) -> None:
        selected = e.control.selected
        if selected:
            self._source = next(iter(selected))

    def _on_provider_change(self, e) -> None:
        selected = e.control.selected
        if selected:
            self._provider = next(iter(selected))
        # Ô profile chỉ hiện với CCS.
        self._ccs_profile_box.visible = self._provider == "ccs"
        self._ccs_profile.error = None
        self._page.update()

    def _toggle_theme(self, e) -> None:
        if self._page.theme_mode == ft.ThemeMode.DARK:
            self._page.theme_mode = ft.ThemeMode.LIGHT
            self._theme_btn.icon = ft.Icons.DARK_MODE_OUTLINED
        else:
            self._page.theme_mode = ft.ThemeMode.DARK
            self._theme_btn.icon = ft.Icons.LIGHT_MODE_OUTLINED
        self._page.update()

    def _on_run_click(self, e) -> None:
        ccs_profile = (self._ccs_profile.value or "").strip()
        # CCS bắt buộc có profile NAME.
        if self._provider == "ccs" and not ccs_profile:
            self._ccs_profile.error = ft.Text("Nhập tên profile CCS")
            self._page.update()
            return
        self._ccs_profile.error = None

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
            provider=self._provider,
            ccs_profile=ccs_profile,
        )
