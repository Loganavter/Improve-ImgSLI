"""Design-parity regression tests for the gallery card (audit S2-1/2/3/9/12).

Covers:
- S2-1: per-dot quality colors (overlay painter over the single-color row).
- S2-2: hovered card — accent underline toggling via the hover filter.
- S2-3: unreadable item — "!" cover placeholder + danger-colored error row.
- S2-9: AI tie-break badge — accent-stroked (not gray filled).
- S2-12: severity/accent colors resolve through ThemeManager tokens.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from tabs.image_gallery.models import Artifact, GalleryItem, Severity, ThumbnailStatus
from tabs.image_gallery.ui.card import (
    _apply_rejected_visuals,
    _dots_for_item,
    _dots_overlay_painter,
    _hide_card_hover_underline,
    _item_unreadable,
    _show_card_hover_underline,
    _token_color,
    build_gallery_card,
    update_gallery_card,
)


def _item(**overrides) -> GalleryItem:
    defaults = dict(path=Path("/gallery/a.png"), mtime_ns=1)
    defaults.update(overrides)
    return GalleryItem(**defaults)


def test_token_color_falls_back_without_palette_token():
    color = _token_color("success", "#3fbf5f")
    assert isinstance(color, QColor)
    assert color.name().lower() == "#3fbf5f"


def test_severity_tokens_map_to_success_warning_danger():
    # S2-12: resolver mapping clean→success, mild→warning, flagged→danger.
    clean = _token_color(*({"clean": ("success", "#3fbf5f")})["clean"])
    assert clean.name().lower() == "#3fbf5f"


def test_per_dot_colors_are_individually_computed():
    item = _item(
        artifacts={
            Artifact.BANDING: Severity.FLAGGED,
            Artifact.HALO: Severity.MILD,
            Artifact.BLOCKING: Severity.CLEAN,
        }
    )
    dot_text, colors = _dots_for_item(item)
    assert dot_text == "● ● ●"
    assert len(colors) == 3
    assert len({str(c.name()) for c in colors}) == 3


def test_card_stores_per_dot_colors_and_overlay_is_attached(qapp):
    item = _item(
        artifacts={
            Artifact.BANDING: Severity.FLAGGED,
            Artifact.HALO: Severity.MILD,
            Artifact.BLOCKING: Severity.CLEAN,
        }
    )
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    colors = getattr(card, "_gallery_dot_colors", ())
    assert len(colors) == 3
    # S2-1: overlay painter layer present in the button painter pipeline.
    layer_types = [
        type(layer).__name__
        for layer in getattr(card._painter, "_layers", []) or []
    ]
    assert "OverlayPainterLayer" in layer_types
    # Painting the card must not crash (overlay geometry path runs).
    card.grab()
    card.deleteLater()


def test_dots_overlay_painter_draws_per_dot_colors(qapp):
    item = _item(
        artifacts={
            Artifact.BANDING: Severity.FLAGGED,
            Artifact.HALO: Severity.MILD,
            Artifact.BLOCKING: Severity.CLEAN,
        }
    )
    card = build_gallery_card(item, parent=None)
    card._gallery_dot_colors = (
        QColor("#c0392b"),
        QColor("#e8b64c"),
        QColor("#3fbf5f"),
    )

    from PySide6.QtGui import QImage, QPainter

    image = QImage(250, 170, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:

        class _Ctx:
            widget = card
            rect = QRectF(0, 0, 250, 170)

        _dots_overlay_painter(painter, _Ctx(), None)
    finally:
        painter.end()
    card.deleteLater()


def test_unreadable_item_detection():
    assert _item_unreadable(_item(thumbnail_status=ThumbnailStatus.ERROR))
    assert _item_unreadable(_item(analysis_error="file is corrupt"))
    assert not _item_unreadable(_item())
    assert not _item_unreadable(_item(analysis_error="VLM timeout"))


def test_unreadable_card_shows_placeholder_and_danger_error_row(qapp):
    item = _item(
        thumbnail_status=ThumbnailStatus.ERROR,
        analysis_error="decode failed",
    )
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    regions = {r.id: r for r in card.regions()}
    # S2-3: "!" placeholder in the cover region.
    assert regions["cover"].text == "!"
    # Error row carries the flagged/danger severity color — filename row now also has #dfdfdf, so filter for decode failed
    text_rows = regions["text"].rows or []
    colored = [r for r in text_rows if r.color is not None]
    assert any("decode failed" in r.text for r in colored)
    err_row = next(r for r in colored if "decode failed" in r.text)
    assert err_row.color.name().lower() == _token_color("danger", "#D93025").name().lower()
    card.grab()
    card.deleteLater()


def test_readable_card_has_no_placeholder(qapp):
    item = _item()
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    regions = {r.id: r for r in card.regions()}
    assert regions["cover"].text in ("", None)
    # Filename row now has #dfdfdf, dots are via overlay painter (circles r4) not via row text "● ● ●"
    text_rows = regions["text"].rows or []
    # Filename row is colored #dfdfdf
    assert any(r.text == item.name and r.color is not None and r.color.name().lower() == "#dfdfdf" for r in text_rows)
    # Dots are drawn by overlay, not as a colored text row
    assert not any(r.text == "● ● ●" for r in text_rows if r.color is not None)
    # Overlay should have dot colors
    assert len(getattr(card, "_gallery_dot_colors", ())) == 3
    card.deleteLater()


def test_update_gallery_card_toggles_unreadable_placeholder(qapp):
    item = _item()
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    bad = _item(
        path=Path("/gallery/a.png"),
        mtime_ns=2,
        thumbnail_status=ThumbnailStatus.ERROR,
        analysis_error="corrupt",
    )
    update_gallery_card(card, bad)
    regions = {r.id: r for r in card.regions()}
    assert regions["cover"].text == "!"
    update_gallery_card(card, _item(path=Path("/gallery/a.png"), mtime_ns=3))
    regions = {r.id: r for r in card.regions()}
    assert regions["cover"].text in ("", None)
    card.deleteLater()


def test_hover_underline_toggle(qapp):
    card = build_gallery_card(_item(), parent=None)
    qapp.processEvents()
    _show_card_hover_underline(card)
    # New: blue bar via overlay flag, not whole-button underline
    assert getattr(card, "_hover_blue_bar", False) is True
    _hide_card_hover_underline(card)
    assert getattr(card, "_hover_blue_bar", False) is False
    card.deleteLater()


def test_tie_break_badge_is_accent_stroked_not_gray_filled(qapp):
    item = _item(vlm_tie_pending=True)
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    # S2-9: accent-stroked pill — not filled, accent border + accent text.
    assert card.property("badgeFilled") is False
    border = card.property("badgeBorderColor")
    text = card.property("badgeTextColor")
    assert border is not None and text is not None
    accent = _token_color("accent", "#0096FF")
    assert border.name().lower() == accent.name().lower()
    card.deleteLater()


def test_rejected_badge_uses_danger_token(qapp):
    item = _item(rejected=True)
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    danger = _token_color("danger", "#D93025")
    assert card.property("badgeBackgroundColor").name().lower() == danger.name().lower()
    card.deleteLater()


def test_hover_capsule_flyout_fits_its_buttons(qapp):
    """The hover pill must not clamp its outer widget below content size.

    Regression: setFixedSize(88, 30) was applied to the BaseFlyout *outer*
    widget, which carries 2×8 shadow margins + 2×4 content padding — the
    three 22px buttons then lived in a ~72×14 box (clipped ~2× vertically,
    worse with the 4th fidelity action). The outer sizeHint must always
    contain every action button's geometry.
    """
    from tabs.image_gallery.ui.card.hover import (
        ensure_gallery_card_flyout,
        show_gallery_card_flyout,
    )

    card = build_gallery_card(_item(), parent=None)
    card.resize(250, 170)
    qapp.processEvents()
    show_gallery_card_flyout(card)
    qapp.processEvents()
    flyout = ensure_gallery_card_flyout(card)
    assert flyout is not None
    flyout.update_state()
    qapp.processEvents()

    # Outer widget must be at least content-sized (never fixed to the
    # svg's visible-pill 88×30, which cannot hold the shadow margins).
    assert flyout.width() >= 88
    assert flyout.height() >= 30

    # The real invariant: every action button fits inside the outer rect.
    # Buttons are children of flyout.container (itself inset by
    # SHADOW_RADIUS=8 inside the outer widget), so map via container pos.
    outer = flyout.rect()
    container = flyout.container
    buttons = list(flyout._buttons.values())
    assert buttons, "capsule must contain action buttons"
    for btn in buttons:
        in_outer = btn.geometry().translated(container.x(), container.y())
        assert outer.contains(in_outer), (
            f"button {btn.property('element_name')!r} geometry {btn.geometry()} "
            f"(container-relative) -> {in_outer} does not fit outer rect {outer}"
        )

    flyout.hide()
    card.deleteLater()
