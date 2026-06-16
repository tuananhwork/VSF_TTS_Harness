"""Design tokens + theme cho Pattern GUI.

Tập trung mọi quyết định hình ảnh ở một chỗ: seed màu, theme sáng/tối, thang
spacing, màu trạng thái, và vài helper dựng control hay dùng. Các screen import
từ đây thay vì rải hex khắp nơi — đổi brand chỉ cần sửa file này.
"""
from __future__ import annotations

from typing import Optional

import flet as ft

# ── Brand ────────────────────────────────────────────────────────────────────
# Seed indigo: Material 3 sinh toàn bộ ColorScheme (sáng & tối) từ một màu này.
SEED = "#4F46E5"

# ── Spacing scale (lưới 4px) ───────────────────────────────────────────────────
XS = 4
SM = 8
MD = 16
LG = 24
XL = 32

# ── Bo góc ─────────────────────────────────────────────────────────────────────
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16

# ── Màu trạng thái (cố định, đọc tốt trên cả nền sáng lẫn tối) ───────────────────
SUCCESS = "#16A34A"
WARNING = "#D97706"
INFO = "#2563EB"

# Màu theo từng mức độ tự tin của skill proposal.
CONFIDENCE = {
    "cao":        {"color": SUCCESS, "label": "Cao"},
    "trung bình": {"color": WARNING, "label": "Trung bình"},
    "thấp":       {"color": "#6B7280", "label": "Thấp"},
}

# ── Token màu phụ thuộc theme (resolve theo ColorScheme runtime) ─────────────────
MUTED = ft.Colors.ON_SURFACE_VARIANT      # text phụ
HAIRLINE = ft.Colors.OUTLINE_VARIANT      # viền mảnh
SURFACE_ALT = ft.Colors.SURFACE_CONTAINER_HIGHEST  # nền card/khối phụ


def build_themes() -> tuple[ft.Theme, ft.Theme]:
    """Trả về (theme sáng, theme tối) dùng chung một seed, Material 3."""
    light = ft.Theme(color_scheme_seed=SEED, use_material3=True)
    dark = ft.Theme(color_scheme_seed=SEED, use_material3=True)
    return light, dark


# ── Helpers dựng control ─────────────────────────────────────────────────────

def hairline(color: str = HAIRLINE, width: int = 1) -> ft.Border:
    """Viền 1px đều 4 cạnh (0.85 không có ft.border.all)."""
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def pad(
    *,
    left: int = 0,
    top: int = 0,
    right: int = 0,
    bottom: int = 0,
) -> ft.Padding:
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)


def pad_all(v: int) -> ft.Padding:
    return ft.Padding(left=v, top=v, right=v, bottom=v)


def pad_xy(x: int, y: int) -> ft.Padding:
    return ft.Padding(left=x, top=y, right=x, bottom=y)


def gap(size: int) -> ft.Container:
    """Khoảng trống dọc cố định giữa các control trong Column."""
    return ft.Container(height=size)


def screen_header(
    title: str,
    subtitle: Optional[str] = None,
    *,
    leading: Optional[ft.Control] = None,
    trailing: Optional[ft.Control] = None,
) -> ft.Control:
    """Header thống nhất cho mọi màn hình: (leading) tiêu đề + phụ đề, (trailing)."""
    title_col = ft.Column(
        [ft.Text(title, theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                 weight=ft.FontWeight.BOLD)],
        spacing=2,
        expand=True,
    )
    if subtitle:
        title_col.controls.append(
            ft.Text(subtitle, theme_style=ft.TextThemeStyle.BODY_SMALL, color=MUTED)
        )

    row_items: list[ft.Control] = []
    if leading is not None:
        row_items.append(leading)
    row_items.append(title_col)
    if trailing is not None:
        row_items.append(trailing)

    return ft.Row(row_items, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                  spacing=MD)


def section_label(text: str) -> ft.Control:
    """Nhãn nhỏ in hoa cho từng nhóm thiết lập."""
    return ft.Text(
        text.upper(),
        theme_style=ft.TextThemeStyle.LABEL_MEDIUM,
        weight=ft.FontWeight.BOLD,
        color=MUTED,
    )


def card(content: ft.Control, *, padding: int = MD) -> ft.Container:
    """Khối card chuẩn: nền surface phụ, viền mảnh, bo góc."""
    return ft.Container(
        content=content,
        bgcolor=SURFACE_ALT,
        border=hairline(),
        border_radius=RADIUS_MD,
        padding=pad_all(padding),
    )
