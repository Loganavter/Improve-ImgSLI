"""``resolve_help_icon`` must return a MONOCHROME icon tinted from the theme.

Falsification: a deliberately two-colour probe (and the real red app icon
``highlight_diff_icon.svg``) carries >1 colour at the source; the same source
routed through :func:`resolve_help_icon` collapses to one theme colour while
transparent pixels stay transparent, and the colour tracks the active theme.

Qt stores pixmaps premultiplied, so a correctly tinted pixel is *not* literally
``(r, g, b) == theme`` at every alpha: at low alpha the 8-bit premultiplied
channel quantizes (a pixel of theme #1f1f1f at alpha 5 stores ``1``, which
un-premultiplies back to 51). The invariant checked here is therefore the exact
one a theme fill obeys: every channel equals ``round(theme_channel * alpha /
255)`` within one quantization step — i.e. the pixel is the theme colour at that
alpha — with hard-edged probes additionally asserted to be an exact singleton.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, qAlpha, qBlue, qGreen, qRed
from PySide6.QtWidgets import QApplication

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from plugins.help.icons import clear_help_icon_cache, resolve_help_icon
from sli_ui_toolkit.theme import ThemeManager
from ui.icon_manager import get_app_icon

_PROBE_NAME = "__help_mono_probe__"
#: Large enough to hit the cached SVG raster directly (see icons._SVG_RASTER_PX).
_RASTER = 256


def _probe_icon() -> QIcon:
    """32x32 red|green top half, fully transparent bottom half (hard edges)."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, 16, 16, QColor("#ff0000"))
    painter.fillRect(16, 0, 16, 16, QColor("#00ff00"))
    painter.end()
    return QIcon(pixmap)


def _probe_resolver(name: str) -> QIcon | None:
    return _probe_icon() if name == _PROBE_NAME else None


def _raw_pixels(icon: QIcon, size: int = _RASTER) -> list[tuple[int, int, int, int]]:
    """Premultiplied RGBA per pixel, as stored (no un-premultiply rounding)."""
    image = icon.pixmap(size, size).toImage()
    return [
        (qRed(p), qGreen(p), qBlue(p), qAlpha(p))
        for y in range(image.height())
        for x in range(image.width())
        for p in (image.pixel(x, y),)
    ]


def _is_theme_shade(rgba: tuple[int, int, int, int], theme: tuple[int, int, int]) -> bool:
    r, g, b, a = rgba
    if a == 0:
        return True
    return all(
        abs(channel - round(token * a / 255)) <= 1
        for channel, token in zip((r, g, b), theme)
    )


@pytest.fixture
def themed(qtbot):
    """App palettes registered; restore the previous theme afterwards."""
    assert QApplication.instance() is not None
    manager = ThemeManager.get_instance()
    previous = manager.get_current_theme()
    manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    manager.set_theme(previous)
    clear_help_icon_cache()
    try:
        yield manager
    finally:
        manager.set_theme(previous)
        clear_help_icon_cache()


def _token_rgb(theme: str, token: str = "dialog.text") -> tuple[int, int, int]:
    palette = DARK_THEME_PALETTE if theme == "dark" else LIGHT_THEME_PALETTE
    color = QColor(palette[token])
    return (color.red(), color.green(), color.blue())


def test_probe_source_is_multicolour(qtbot):
    """Falsification: the raw probe really carries more than one colour."""
    assert QApplication.instance() is not None
    opaque = {
        (r, g, b) for r, g, b, a in _raw_pixels(_probe_icon(), 32) if a > 0
    }
    assert len(opaque) > 1


def test_resolved_probe_is_exact_singleton(themed):
    themed.set_theme("light")
    pixels = _raw_pixels(resolve_help_icon(_PROBE_NAME, resolvers=(_probe_resolver,)), 32)
    opaque = {(r, g, b) for r, g, b, a in pixels if a > 0}
    assert opaque == {_token_rgb("light")}
    # The unpainted bottom half is still fully transparent.
    assert any(a == 0 for _, _, _, a in pixels)
    assert all(a == 255 or a == 0 for _, _, _, a in pixels)


def test_colour_follows_theme(themed):
    themed.set_theme("light")
    light = _raw_pixels(resolve_help_icon(_PROBE_NAME, resolvers=(_probe_resolver,)), 32)
    light_opaque = {(r, g, b) for r, g, b, a in light if a > 0}
    themed.set_theme("dark")
    dark = _raw_pixels(resolve_help_icon(_PROBE_NAME, resolvers=(_probe_resolver,)), 32)
    dark_opaque = {(r, g, b) for r, g, b, a in dark if a > 0}
    assert light_opaque == {_token_rgb("light")}
    assert dark_opaque == {_token_rgb("dark")}
    assert light_opaque != dark_opaque


def test_real_coloured_app_icon_is_monochrome(themed):
    themed.set_theme("light")
    theme = _token_rgb("light")

    source = _raw_pixels(get_app_icon("highlight_diff_icon.svg"))
    source_coloured = [
        (r, g, b) for r, g, b, a in source if a > 0 and not (r == g == b)
    ]
    assert source_coloured, "expected the red highlight_diff icon to raster coloured"

    resolved = _raw_pixels(resolve_help_icon("highlight_diff_icon.svg"))
    assert resolved, "expected a raster"
    assert all(_is_theme_shade(px, theme) for px in resolved)
    # At least one fully opaque pixel is exactly the theme colour.
    assert (theme[0], theme[1], theme[2], 255) in resolved


def test_fallback_icon_is_monochrome(themed):
    themed.set_theme("light")
    theme = _token_rgb("light")
    resolved = _raw_pixels(resolve_help_icon(None))
    assert resolved
    assert all(_is_theme_shade(px, theme) for px in resolved)
    assert (theme[0], theme[1], theme[2], 255) in resolved
