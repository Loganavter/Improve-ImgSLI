from __future__ import annotations

from typing import Any

from PyQt6.QtGui import QColor

def build_theme_colors(widget) -> dict[str, Any]:
    tm = widget.theme_manager
    is_dark = tm.is_dark()
    text_col = tm.get_color("WindowText")
    if is_dark:
        return {
            "is_dark": is_dark,
            "accent": tm.get_color("accent"),
            "text_col": text_col,
            "canvas_bg": tm.get_color("Window"),
            "gutter_bg": QColor(42, 42, 46),
            "group_bg": QColor(46, 46, 50),
            "track_bg": tm.get_color("AlternateBase"),
            "lane_bg": QColor(50, 50, 55),
            "grid_col": tm.get_color("separator.color"),
            "footer_bg": QColor(38, 38, 42),
            "sep_strong": tm.get_color("dialog.border"),
            "sep_soft": QColor(55, 55, 60),
            "sb_idle": QColor(255, 255, 255, 55),
            "sb_hover": QColor(255, 255, 255, 85),
        }
    return {
        "is_dark": is_dark,
        "accent": tm.get_color("accent"),
        "text_col": text_col,
        "canvas_bg": tm.get_color("Window"),
        "gutter_bg": QColor(244, 244, 246),
        "group_bg": QColor(250, 250, 252),
        "track_bg": QColor(242, 243, 246),
        "lane_bg": QColor(248, 248, 250),
        "grid_col": QColor(220, 220, 225),
        "footer_bg": QColor(236, 238, 242),
        "sep_strong": QColor(188, 192, 200),
        "sep_soft": QColor(218, 220, 226),
        "sb_idle": QColor(0, 0, 0, 65),
        "sb_hover": QColor(0, 0, 0, 95),
    }

def track_color(widget, track_kind: str, channel_kind: str | None = None) -> QColor:
    accent = QColor(widget.theme_manager.get_color("accent"))
    if channel_kind == "bool" or track_kind == "bool":
        return QColor(0, 140, 198)
    if channel_kind == "enum" or track_kind == "enum":
        return QColor(180, 88, 28)
    if channel_kind == "state" or track_kind == "state":
        return QColor(100, 100, 116)
    if channel_kind == "vec2" or track_kind == "vec2":
        return QColor(34, 140, 94)
    return accent

def track_line_color(widget, track_id: str, track_kind: str, channel_kind: str | None = None) -> QColor:
    if track_id == "comparison.diff_mode":
        return QColor(0, 140, 198)
    return track_color(widget, track_kind, channel_kind)

def track_value_color(
    widget,
    *,
    track_id: str,
    track_kind: str,
    channel_kind: str | None,
    value,
    fallback: QColor | None = None,
) -> QColor:
    fallback_color = QColor(fallback) if fallback is not None else track_color(
        widget, track_kind, channel_kind
    )
    return fallback_color

def mix_colors(base: QColor, overlay: QColor, alpha: int) -> QColor:
    alpha_ratio = max(0.0, min(1.0, alpha / 255.0))
    inv = 1.0 - alpha_ratio
    return QColor(
        int(base.red() * inv + overlay.red() * alpha_ratio),
        int(base.green() * inv + overlay.green() * alpha_ratio),
        int(base.blue() * inv + overlay.blue() * alpha_ratio),
    )

def group_content_bg(widget, base_bg: QColor, group, strength: int) -> QColor:
    for track in group.tracks.values():
        visible_channels = getattr(widget, "_visible_channels")(track)
        if visible_channels:
            accent = track_color(widget, track.kind, visible_channels[0].kind)
            break
    else:
        accent = QColor(widget.theme_manager.get_color("accent"))
    return mix_colors(base_bg, accent, strength)
