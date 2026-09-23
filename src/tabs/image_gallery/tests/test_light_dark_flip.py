"""Light ↔ dark theme flip regression tests for the gallery (W4).

Asserts that gallery token resolution tracks ``src/resources/themes.json``
hex-for-hex in BOTH themes, and that the key repaint-subscribed widgets
(``StatsStrip``, grid ``_SeriesHeaderBar``) re-resolve and repaint without
crashing offscreen across a light → dark → light round-trip.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QColor

from tabs.image_gallery.ui.grid_view import _SeriesHeaderBar
from tabs.image_gallery.ui.stats_strip import StatsStrip

# Gallery + substrate tokens whose W1 light values carry the contrast norm
# (design.md "Light-theme contrast norm"). Expected hexes are read LIVE from
# themes.json — never duplicated here.
GALLERY_TOKENS = (
    "gallery.card.background",
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
    tm = _w1_palettes
    data = _themes_data()

    strip = StatsStrip()
    qtbot.addWidget(strip)
    strip.set_stats(40, 7, 33)
    accent_bar = _SeriesHeaderBar(collapsible=True)
    qtbot.addWidget(accent_bar)
    plain_bar = _SeriesHeaderBar(collapsible=False)
    qtbot.addWidget(plain_bar)

    for theme in ("light", "dark", "light"):
        _set_theme(tm, qapp, theme)
        light = data[theme]
        assert strip._stats_bg.name().lower() == QColor(light["gallery.stats.background"]).name().lower()
        assert accent_bar._bar_color.name().lower() == QColor(light["gallery.accent.bar"]).name().lower()
        assert plain_bar._bar_color.name().lower() == QColor(light["dialog.border"]).name().lower()
        # Repaint paths must not crash offscreen on any theme.
        assert not strip.grab().isNull()
        assert not accent_bar.grab().isNull()
        assert not plain_bar.grab().isNull()

    # Round-trip lands back on the light production values.
    assert strip._stats_bg.name().lower() == "#8a8a8a"
    assert accent_bar._bar_color.name().lower() == "#0078d4"
