"""Font-settings flyout sync for ``MultiCompareWidget``.

Split out of ``widget.py`` to keep that class down to composition/wiring --
mirrors the ``drag_drop`` split. Every function here takes the widget as its
first argument and reads/writes its instance state directly.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from tabs.multi_compare.models import MultiCompareLabelSettings
from tabs.multi_compare.scene import actions


def sync_font_settings_flyout(widget) -> None:
    from domain.qt_adapters import ensure_visible_qcolor
    from domain.types import Color

    st = widget.state.label_settings
    widget.font_settings_flyout.set_values(
        st.font_size_percent,
        st.font_weight,
        ensure_visible_qcolor(st.text_rgba, fallback=Color(255, 255, 255, 255)),
        ensure_visible_qcolor(st.bg_rgba, fallback=Color(0, 0, 0, 255)),
        st.draw_background,
        "edges",
        st.text_alpha_percent,
    )


def toggle_font_settings_flyout(widget) -> None:
    if widget._font_popup_open:
        widget.font_settings_flyout.hide()
        return
    show_font_settings_flyout(widget)


def show_font_settings_flyout(widget) -> None:
    """Open the text flyout without toggle-close (Find Action reveal/run)."""
    if widget._font_popup_open:
        return
    sync_font_settings_flyout(widget)
    widget.font_settings_flyout.show_aligned(
        widget.toolbar.btn_text_settings,
        anchor_point="bottom-right",
        flyout_point="top-left",
        offset=10,
        animation="slide-fade",
    )
    if hasattr(widget.toolbar.btn_text_settings, "setFlyoutOpen"):
        widget.toolbar.btn_text_settings.setFlyoutOpen(True)
    widget._font_popup_open = True


def on_font_settings_closed(widget) -> None:
    widget._font_popup_open = False
    if hasattr(widget.toolbar.btn_text_settings, "setFlyoutOpen"):
        widget.toolbar.btn_text_settings.setFlyoutOpen(False)


def on_font_settings_changed(
    widget,
    size: int,
    weight: int,
    color: QColor,
    bg_color: QColor,
    draw_bg: bool,
    _placement: str,
    opacity: int,
) -> None:
    settings = MultiCompareLabelSettings(
        font_size_percent=max(1, int(size)),
        font_weight=max(0, int(weight)),
        text_rgba=(
            color.red(),
            color.green(),
            color.blue(),
            color.alpha(),
        ),
        bg_rgba=(
            bg_color.red(),
            bg_color.green(),
            bg_color.blue(),
            bg_color.alpha(),
        ),
        draw_background=bool(draw_bg),
        text_alpha_percent=max(0, min(100, int(opacity))),
    )
    widget.store.dispatch(actions.set_label_settings(settings))
