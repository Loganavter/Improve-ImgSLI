"""Recent card hover renders as an overlay wash on top of the cover preview.

Regression: hover used to be an opaque ``BackgroundLayer`` repaint under the
content — invisible over the cover pixmap, and a solid color swap on the text
strip. The fix adds a widget-scoped ``overlay_painter=`` wash that paints a
translucent overlay over the whole card (cover included).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap

from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.cards import _card_hover_wash, build_grid_card
from tabs.session_picker.recent.selection import apply_card_selected


def _record(tmp_path, name: str = "proj.imgsli") -> RecentProjectRecord:
    path = tmp_path / name
    path.write_text("{}")
    return RecentProjectRecord(
        path=str(path),
        display_name=name,
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )


def _cover_pixel(card) -> QColor:
    """Center of the cover region (top strip of the grid card)."""
    return card.grab().toImage().pixelColor(card.width() // 2, 8)


def _text_pixel(card) -> QColor:
    """Middle of the text strip (bottom half of the grid card)."""
    return card.grab().toImage().pixelColor(card.width() // 2, card.height() - 12)


def _hover_cover(card) -> None:
    """Simulate the pointer over the cover region (the events mixin path)."""
    card._hovered_region = "cover"
    card.update()


def test_grid_card_wires_hover_wash(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tabs.session_picker.recent.cards.preview_for_record",
        lambda _record: QPixmap(64, 36),
    )
    card = build_grid_card(
        _record(tmp_path),
        parent=None,
        tr=lambda key, default="", **kw: default or key,
        on_activate=lambda *_: None,
        on_context_menu=lambda *_: None,
    )
    try:
        # overlay_painter is the documented public hook for on-top painting.
        assert card._painter.layers[-1]._painter_fn is _card_hover_wash
    finally:
        card.deleteLater()


def test_grid_card_hover_washes_over_cover_preview(qapp, tmp_path, monkeypatch):
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("light", qapp)

    thumb = QPixmap(64, 36)
    thumb.fill(QColor("#40a0e0"))
    monkeypatch.setattr(
        "tabs.session_picker.recent.cards.preview_for_record",
        lambda _record: thumb,
    )
    card = build_grid_card(
        _record(tmp_path),
        parent=None,
        tr=lambda key, default="", **kw: default or key,
        on_activate=lambda *_: None,
        on_context_menu=lambda *_: None,
    )
    try:
        idle_cover = _cover_pixel(card)
        idle_text = _text_pixel(card)

        _hover_cover(card)
        hover_cover = _cover_pixel(card)
        hover_text = _text_pixel(card)

        # Hover must visibly wash the cover preview (was invisible before the
        # overlay fix — the opaque hover fill sat behind the pixmap).
        assert hover_cover != idle_cover
        assert (
            hover_cover.red() + hover_cover.green() + hover_cover.blue()
            < idle_cover.red() + idle_cover.green() + idle_cover.blue()
        ), "light-theme wash darkens the cover preview"
        # Same wash over the text strip — not an opaque swap to the theme
        # hover token.
        assert hover_text != idle_text

        # Selection locks the background: hover must not wash over the fill.
        apply_card_selected(card, True)
        card.update()
        selected_cover = _cover_pixel(card)
        _hover_cover(card)
        assert _cover_pixel(card) == selected_cover
    finally:
        card.deleteLater()
        tm.set_theme("light", qapp)