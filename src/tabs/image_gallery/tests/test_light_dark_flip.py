"""Light ↔ dark theme flip regression tests for the gallery (W4).

Asserts that gallery token resolution tracks ``src/resources/themes.json``
hex-for-hex in BOTH themes, and that the key repaint-subscribed widgets
(``StatsStrip``, grid series-header accent layers) re-resolve and repaint
without crashing offscreen across a light → dark → light round-trip.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QColor

from tabs.image_gallery.ui.grid_view import _resolve_section_bar_color
from tabs.image_gallery.ui.stats_strip import StatsStrip

# Gallery + substrate tokens whose W1 light values carry the contrast norm
# (design.md "Light-theme contrast norm"). Expected hexes are read LIVE from
# themes.json — never duplicated here.
GALLERY_TOKENS = (
    "gallery.card.background",
    "gallery.card.border",
    "gallery.card.hover",
    "gallery.stats.background",
    "gallery.stats.text",
    "gallery.header.text",
    "gallery.footer.text",
    "gallery.grid.background",
    "gallery.status.ok",
    "gallery.status.warn",
    "gallery.status.danger",
    "gallery.accent.bar",
    "gallery.accent.text",
    "separator.color",
    "surface.background",
    "Window",
    "accent",
)


def _themes_data() -> dict:
    from utils.resource_loader import resource_path

    with open(resource_path("resources/themes.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def _w1_palettes(qapp):
    """Register production W1 palettes; teardown restores the bare manager."""
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    prev_theme = tm.get_current_theme()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    yield tm
    try:
        tm.register_palettes({}, {})
        tm.set_theme(prev_theme, qapp, await_ripples=False)
        try:
            tm._flush_pending_theme()  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception:
        pass


def _set_theme(tm, qapp, name: str) -> None:
    tm.set_theme(name, qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass
    qapp.processEvents()


def test_gallery_tokens_match_themes_json_in_both_themes(qapp, _w1_palettes) -> None:
    """Every gallery/substrate token resolves to the live themes.json hex."""
    from ui.theming import try_resolve_theme_color

    tm = _w1_palettes
    data = _themes_data()
    for theme in ("light", "dark"):
        _set_theme(tm, qapp, theme)
        assert tm.get_current_theme() == theme
        assert tm.is_dark() == (theme == "dark")
        for token in GALLERY_TOKENS:
            resolved = try_resolve_theme_color(tm, token)
            assert resolved is not None, f"{token} unresolvable under {theme}"
            expected = QColor(data[theme][token]).name().lower()
            got = (resolved if isinstance(resolved, QColor) else QColor(resolved)).name().lower()
            assert got == expected, f"{token} under {theme}: {got} != themes.json {expected}"


def test_stats_strip_and_section_bars_repaint_on_flip(qtbot, qapp, _w1_palettes) -> None:
    """StatsStrip + grid section bars track the flip and repaint offscreen."""
    from pathlib import Path

    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.widget import ImageGalleryWidget

    def _hex(color) -> str:
        return (color if isinstance(color, QColor) else QColor(color)).name().lower()

    tm = _w1_palettes
    data = _themes_data()

    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_stats(40, 7, 33)
    items = [GalleryItem(path=Path(f"/gallery/{n}.png"), mtime_ns=i) for i, n in enumerate("abcd")]
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    w.rebuild_grid(items)
    w._grid_view.set_series([items[:2]], hub_names=["HUB-A"], collapsed={})
    btn = w._grid_view.findChild(object, "GallerySeriesHeaderBtn_0")
    assert btn is not None

    for theme in ("light", "dark", "light"):
        _set_theme(tm, qapp, theme)
        light = data[theme]
        assert strip._stats_bg.name().lower() == QColor(light["gallery.stats.background"]).name().lower()
        assert _hex(_resolve_section_bar_color(True)) == QColor(light["gallery.accent.bar"]).name().lower()
        assert _hex(_resolve_section_bar_color(False)) == QColor(light["dialog.border"]).name().lower()
        # Repaint paths must not crash offscreen on any theme.
        assert not strip.grab().isNull()
        assert not btn.grab().isNull()

    # Round-trip lands back on the light production values.
    assert strip._stats_bg.name().lower() == "#ffffff"
    assert _hex(_resolve_section_bar_color(True)) == "#0096ff"


def test_normal_card_shows_border_edge_in_light(qtbot, qapp, _w1_palettes) -> None:
    """Normal (non-BEST, non-rejected) cards render a visible edge in light.

    ``visuals._card_border_color`` repoints the default border to
    ``gallery.card.border`` (``#e2e4e8``); leader cards share the same default
    frame (only the #N pill marks them) and rejected/danger paths are
    untouched. Asserts the override resolves hex-exact AND that an
    offscreen grab shows an edge pixel distinct from the card fill (the
    painter blends the 1px hairline, so the pixel need not equal the hex —
    it must differ from the fill).
    """
    from pathlib import Path

    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.ui.card import build_gallery_card

    tm = _w1_palettes
    _set_theme(tm, qapp, "light")
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = build_gallery_card(item, parent=None)
    qtbot.addWidget(card)
    card.show()
    qtbot.waitExposed(card)
    qapp.processEvents()
    assert card.borderColor().name().lower() == "#e2e4e8"
    img = card.grab().toImage()
    assert not img.isNull()
    w, h = img.width(), img.height()
    fill = img.pixelColor(4, h // 2).name().lower()
    # The 1px hairline may land at x=0 or x=1 (DPR rounding, and it shifts
    # under parallel load); scan the left band for the edge pixel instead of
    # reading a single fixed column.
    band = [img.pixelColor(x, h // 2).name().lower() for x in range(0, 4)]
    edge = next((px for px in band if px != fill), band[0])
    assert edge != fill, f"no border edge in {band} (fill {fill}): border invisible in light"
    # The overlay strokes the override (not an AA accident): the edge pixel
    # must sit near the border hex and far from the fill. NOTE: since the
    # shelf-style card base (variant default tint, not pinned white), the
    # 1px AA-blended edge pixel leans toward the tinted fill — assert the
    # border token is wired and the edge visibly differs from the fill.
    from PySide6.QtGui import QColor as _QC

    _edge, _bord, _fill = _QC(edge), _QC("#e2e4e8"), _QC(fill)

    def _dist(a, b):
        return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())

    assert _dist(_edge, _fill) > 12, f"edge {edge} == fill {fill}: border invisible"
    assert _dist(_edge, _bord) < 120, f"edge {edge} too far from border #e2e4e8"
    card.deleteLater()


def test_stats_strip_paints_border_edge_in_light(qtbot, qapp, _w1_palettes) -> None:
    """StatsStrip strokes the ``gallery.card.border`` hairline in light.

    The strip fill is ``#ffffff`` like the cards (white-cards philosophy);
    separation comes from the 1px rounded border painted in ``paintEvent``.
    Asserts the cached border resolves hex-exact AND that the grabbed top
    edge differs from the strip fill.
    """
    tm = _w1_palettes
    _set_theme(tm, qapp, "light")
    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.show()
    qapp.processEvents()
    assert strip._stats_border.name().lower() == "#e2e4e8"
    img = strip.grab().toImage()
    assert not img.isNull()
    sw, sh = img.width(), img.height()
    edge = img.pixelColor(sw // 2, 0).name().lower()
    fill = img.pixelColor(sw // 2, sh // 2).name().lower()
    assert edge != fill, f"strip edge {edge} == fill {fill}: border invisible in light"
