from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def resolve_clear_color(widget) -> QColor:
    plan = getattr(widget, "_active_render_plan", None)
    fill_rgba = getattr(plan, "fill_rgba", None)
    if bool(getattr(widget, "_use_plan_fill_clear", False)):
        # Export offscreen: plan fill paints the virtual-canvas chrome. When
        # fill is off, clear must stay transparent so pad pixels remain
        # alpha=0 (theme clear would bake an opaque wrong color that
        # ``apply_background_fill`` cannot replace).
        if fill_rgba is not None and len(fill_rgba) >= 4:
            return QColor(
                int(fill_rgba[0]),
                int(fill_rgba[1]),
                int(fill_rgba[2]),
                int(fill_rgba[3]),
            )
        return QColor(0, 0, 0, 0)

    # Live QRhiWidget sits under a WA_TranslucentBackground CSD shell. Any
    # clear alpha < 255 punches through to the desktop on Windows/D3D
    # (see docs/dev/rendering/render-pass-contract.md + qrhi-gotchas).
    # Match Multi Compare's ``_theme_or_palette_bg`` opaque rule.
    color = getattr(widget, "_theme_background_color", None)
    if isinstance(color, QColor) and color.isValid():
        out = QColor(color)
        out.setAlpha(255)
        return out

    palette = widget.palette()
    color = palette.color(QPalette.ColorRole.Window)
    if not color.isValid():
        color = palette.color(QPalette.ColorRole.Base)
    if not color.isValid():
        color = QColor(245, 245, 245)
    color.setAlpha(255)
    return color


def render_clear_frame(widget, command_buffer) -> bool:
    """Run the tab RHI renderer; return whether a pass was actually recorded."""
    return bool(
        widget._rhi_renderer.render(
            widget, command_buffer, resolve_clear_color(widget)
        )
    )
