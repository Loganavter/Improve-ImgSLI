"""Design-parity regression tests for the gallery card (audit S2-1/2/3/9/12).

Covers:
- S2-1: per-dot quality colors (overlay painter over the single-color row).
- S2-2: hovered card — accent underline toggling via the hover filter.
- S2-3: unreadable item — "!" cover placeholder + danger-colored error row.
- S2-9 (verdict update): tie-pending falls through to the rank path (#N
  if ranked, else no badge); the leader shows #N — no star/tie-break pills.
- S2-12: severity/accent colors resolve through ThemeManager tokens.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from tabs.image_gallery.models import Artifact, GalleryItem, Severity, ThumbnailStatus
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.tests._activity_fixtures import mark_analyzing
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

import pytest


@pytest.fixture()
def _production_dark_palettes(qapp):
    """Register production palettes under the dark theme.

    Rule A flipped the bare-manager fallbacks to light, so the dark-pin
    assertions below now boot the real dark palette and assert production
    hexes. Teardown restores the bare manager for the fallback-literal
    tests elsewhere in this file.
    """
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    prev_theme = tm.get_current_theme()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("dark", qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass
    yield tm
    try:
        tm.register_palettes({}, {})
        tm.set_theme(prev_theme, qapp, await_ripples=False)
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass


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
    # One dot per measured metric axis, colored by the domain score band.
    item = _item(
        metrics={
            "sharpness": 320.0,  # good
            "noise": 0.9,  # bad
            "white_balance": 0.5,  # mid
        }
    )
    dot_text, colors = _dots_for_item(item, mode="camera")
    assert dot_text == "● ● ●"  # legacy constant, not authoritative
    # Only the MEASURED axes are dotted once anything is measured (the owner
    # 2026-10-22 rule): the three metrics above, in camera registry order.
    assert len(colors) == 3
    assert len({str(c.name()) for c in colors}) >= 3


def test_card_stores_per_dot_colors_and_overlay_is_attached(qapp):
    item = _item(
        metrics={
            "sharpness": 320.0,
            "noise": 0.9,
            "white_balance": 0.5,
        }
    )
    card = build_gallery_card(item, parent=None, mode="camera")
    qapp.processEvents()
    colors = getattr(card, "_gallery_dot_colors", ())
    # Measured axes only (gaps suppressed): sharpness, noise, white_balance.
    assert len(colors) == 3
    assert len(getattr(card, "_gallery_dot_infos", ())) == len(colors)
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

    # Content identity: every configured dot colour must actually be painted.
    # (The previous version had no assertions — a no-op or wrong-colour painter
    # passed despite the test name promising per-dot colours.)
    seen = {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
    }
    assert "#c0392b" in seen, "flagged dot colour not painted"
    assert "#e8b64c" in seen, "mild dot colour not painted"
    assert "#3fbf5f" in seen, "clean dot colour not painted"
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
    # Placeholder dots are an in-progress affordance: mark the item analyzing.
    item = mark_analyzing(_item())
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
    # Overlay should have one dot per measured axis for the item's mode (None
    # → the mode-independent measured set).
    assert len(getattr(card, "_gallery_dot_colors", ())) == len(
        measured_axes_for(None)
    )
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


def test_rebind_clears_hover_and_menu_state(qapp):
    """Pooled-card rebind must not carry hover/menu state to another item.

    Regression: ``_hover_blue_bar`` / ``_gallery_open_menu`` survived
    ``update_gallery_card`` rebinding, so a context menu left open across a
    grid rebuild cleared the moved widget and the underline surfaced on an
    unrelated card. Same-path in-place updates (thumbnail arrival) keep the
    live hover.
    """
    card = build_gallery_card(_item(path=Path("/gallery/a.png")), parent=None)
    qapp.processEvents()
    _show_card_hover_underline(card)
    card._gallery_open_menu = object()
    assert card._hover_blue_bar is True

    update_gallery_card(card, _item(path=Path("/gallery/a.png"), mtime_ns=2))
    assert card._hover_blue_bar is True
    assert getattr(card, "_gallery_open_menu", None) is not None

    update_gallery_card(card, _item(path=Path("/gallery/b.png"), mtime_ns=3))
    assert getattr(card, "_hover_blue_bar", False) is False
    assert getattr(card, "_gallery_open_menu", None) is None
    card.deleteLater()


def test_tie_pending_falls_through_to_rank_path(qapp, _production_dark_palettes):
    # Design verdict: the tie-break pill is removed. Tie-pending items fall
    # through to the rank path — #N if ranked, else no badge (never a
    # tie-break pill). Toolkit badge stays cleared either way.
    from tabs.image_gallery.services.rank_badge import stamp_badges

    item = _item(vlm_tie_pending=True)
    stamp_badges([item])
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    assert card.property("badgeText") in (None, "")
    assert getattr(card, "_gallery_badge", None) is None
    card.deleteLater()
    ranked = _item(vlm_tie_pending=True, rank=3)
    stamp_badges([ranked])
    card = build_gallery_card(ranked, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, ranked)
    assert card.property("badgeText") in (None, "")
    assert getattr(card, "_gallery_badge", None) == "#3"
    _filled, _bg, _bd, txt = card._gallery_badge_style
    assert _filled is True
    # Dark palette: badge ink is the dark `button.primary.text` (#ffffff) —
    # a fixed black was invisible on the dark `button.toggle.background.checked`
    # (#555555) rank pill (≈2.79:1).
    assert txt.name().lower() == "#ffffff"
    card.deleteLater()


def test_best_card_shows_best_pill_with_accent_frame(qapp, _production_dark_palettes):
    from tabs.image_gallery.services.rank_badge import stamp_badges

    item = _item(is_best=True)
    stamp_badges([item])
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    # Design (mockup v2-triage): the series winner shows the ★ BEST preset —
    # an accent pill and an accent frame — never a number, never a ranker label.
    assert card.property("badgeText") in (None, "")
    assert getattr(card, "_gallery_badge", None) == "★ BEST"
    _filled, _bg, _bd, txt = card._gallery_badge_style
    assert _filled is True
    assert card.borderColor().name().lower() == _bg.name().lower()  # accent frame
    card.deleteLater()


def test_rank_pill_text_tracks_theme_and_clears_contrast(qapp, _production_dark_palettes):
    """#N ink follows ``button.primary.text``: #000000 light / #ffffff dark.

    Red-before/green-after: the previous ink was a hardcoded ``#000000`` in
    both themes, which measured ≈2.79:1 against the dark rank pill
    (``button.toggle.background.checked`` = ``#555555``). The tokenised ink
    keeps each theme's pill legible (>= 4.5:1, WCAG AA body text).
    """
    import json

    from sli_ui_toolkit.managers import ThemeManager
    from utils.resource_loader import resource_path

    with open(resource_path("resources/themes.json"), encoding="utf-8") as f:
        data = json.load(f)

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def _lum(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        if len(h) == 8:  # ARGB
            h = h[2:]
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    def _ratio(a: str, b: str) -> float:
        la, lb = _lum(a), _lum(b)
        hi, lo = (la, lb) if la >= lb else (lb, la)
        return (hi + 0.05) / (lo + 0.05)

    tm = ThemeManager.get_instance()
    for theme, expected_ink in (("light", "#000000"), ("dark", "#ffffff")):
        tm.set_theme(theme, qapp, await_ripples=False)
        try:
            tm._flush_pending_theme()  # type: ignore[attr-defined]
        except Exception:
            pass
        qapp.processEvents()
        item = _item(rank=2)  # a NON-winner: the #N rank pill (best shows ★ BEST)
        from tabs.image_gallery.services.rank_badge import stamp_badges

        stamp_badges([item])
        card = build_gallery_card(item, parent=None)
        qapp.processEvents()
        _apply_rejected_visuals(card, item)
        assert getattr(card, "_gallery_badge", None) == "#2"
        _filled, _bg, _bd, txt = card._gallery_badge_style
        assert txt.name().lower() == expected_ink
        pill = data[theme]["button.toggle.background.checked"]
        assert _ratio(expected_ink, pill) >= 4.5, (
            f"{theme}: rank ink {expected_ink} on {pill}: "
            f"{_ratio(expected_ink, pill):.2f} < 4.5"
        )
        card.deleteLater()


def test_rank_badge_ink_falls_back_theme_aware(qapp):
    """Bare manager (no palette) → light default ink #000000, never a crash."""
    from types import SimpleNamespace

    card = build_gallery_card(_item(), parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(
        card,
        SimpleNamespace(
            rejected=False,
            is_best=False,
            vlm_tie_pending=False,
            rank=3,
            crown_rank=None,
            badge="#3",
            badge_kind="rank",
        ),
    )
    assert getattr(card, "_gallery_badge", None) == "#3"
    _filled, _bg, _bd, txt = card._gallery_badge_style
    assert txt.name().lower() == "#000000"
    card.deleteLater()


def test_source_card_shows_source_badge(qapp):
    """A source item's card shows the same 'SOURCE' string as the strip."""
    from tabs.image_gallery.services.rank_badge import stamp_badges

    item = _item(rank=1)
    stamp_badges([item], str(item.path))
    assert item.badge == "SOURCE"
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    assert getattr(card, "_gallery_badge", None) == "SOURCE"
    card.deleteLater()


def test_unreadable_cover_has_plate_background(qapp):
    item = _item(
        thumbnail_status=ThumbnailStatus.ERROR,
        analysis_error="decode failed",
    )
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    regions = {r.id: r for r in card.regions()}
    assert regions["cover"].text == "!"
    assert regions["cover"].override_bg_color is not None
    card.deleteLater()


def test_rejected_sets_no_toolkit_badge(qapp):
    """Rejected cards carry no toolkit badge — dim + strike signal the state.

    No corner mode switch: the only rejected signals are the dim +
    strike-through (card actions live in the right-click context menu).
    """
    item = _item(rejected=True)
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    assert getattr(card, "_badge", None) is None
    assert getattr(card, "_gallery_badge", None) is None
    card.deleteLater()


def test_rejected_dim_is_painter_wash_not_effect(qapp):
    """Rejected dim must not use QGraphicsOpacityEffect (it dimmed children).

    The effect covered the whole subtree INCLUDING the hover capsule (a
    child of the card), washing it out to near-invisible. The overlay
    wash dims only the card's own paint: effect-equivalent mix
    (substrate @0.62 over black cover ≈ 158 gray), children crisp.
    """
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    item = _item(rejected=True)
    card = build_gallery_card(item, parent=None)
    card.resize(250, 170)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    assert not isinstance(card.graphicsEffect(), QGraphicsOpacityEffect)
    card.show()
    qapp.processEvents()
    px = card.grab().toImage().pixelColor(125, 60)
    # Black cover blended toward the light substrate: clearly lifted from
    # 0 (dim applied) but far from plain white (not a white-out).
    assert 80 <= px.red() <= 220
    assert abs(px.red() - px.green()) <= 8 and abs(px.red() - px.blue()) <= 8
    card.deleteLater()
def test_card_bg_is_not_substrate_color_light_theme(monkeypatch) -> None:
    """Card fill must differ from the substrate in the light theme.

    ``gallery.card.background`` is a registered token (W1); the resolver
    chain still prefers ``surface.list`` over ``surface.background`` so a
    missing card token can never paint the exact substrate color. This test
    pins that chain order with a mocked resolver table.
    """
    from unittest.mock import patch

    from tabs.image_gallery.ui import card as card_mod

    table = {
        "surface.list": QColor(240, 240, 240),
        "surface.background": QColor(255, 255, 255),
    }

    def fake_resolve(tm, token):
        return table.get(token)

    with patch("ui.theming.try_resolve_theme_color", side_effect=fake_resolve):
        bg = card_mod._gallery_card_bg()
    assert (bg.red(), bg.green(), bg.blue()) == (240, 240, 240)
    assert (bg.red(), bg.green(), bg.blue()) != (255, 255, 255)


def test_card_hover_is_shelf_wash_not_opaque_swap(monkeypatch) -> None:
    """Hover must be the shelf-style translucent wash, not an opaque bg swap."""
    from unittest.mock import patch

    from tabs.image_gallery.ui.card import painters as painters_mod

    table = {
        "recent.card.hover_wash": QColor(0, 0, 0, 26),
    }

    def fake_resolve(tm, token):
        return table.get(token)

    class FakeTM:
        def is_dark(self) -> bool:
            return False

    with patch("ui.theming.try_resolve_theme_color", side_effect=fake_resolve):
        with patch(
            "sli_ui_toolkit.managers.ThemeManager.get_instance",
            return_value=FakeTM(),
        ):
            wash = painters_mod._gallery_hover_wash_color(None)
    assert wash is not None
    assert wash.alpha() == 26  # translucent, like the recent-projects shelf
    assert (wash.red(), wash.green(), wash.blue()) == (0, 0, 0)


def test_card_regions_keep_transparent_hover(qapp) -> None:
    """Bg/text/cover regions must not pin opaque fills or hover repaints."""
    card = build_gallery_card(_item(), parent=None)
    qapp.processEvents()
    regions = {r.id: r for r in card.regions()}
    assert regions["bg"].override_bg_color is None
    assert regions["text"].override_bg_color is None
    for rid in ("bg", "text", "cover"):
        hc = getattr(regions[rid], "hover_color", None)
        assert hc is not None and hc.alpha() == 0
    card.deleteLater()


def test_best_preset_renders_the_shared_badge(qapp, _production_dark_palettes):
    """The card renders the SHARED badge (single source of truth): a winner
    stamped by ``stamp_badges`` as ★ BEST renders the accent preset verbatim —
    the card never re-derives it from flags."""
    from tabs.image_gallery.services.rank_badge import KIND_BEST, stamp_badges

    item = _item(is_best=True, rank=1)
    stamp_badges([item])
    assert (item.badge, item.badge_kind) == ("★ BEST", KIND_BEST)
    card = build_gallery_card(item, parent=None)
    qapp.processEvents()
    _apply_rejected_visuals(card, item)
    assert getattr(card, "_gallery_badge", None) == "★ BEST"
    card.deleteLater()
