"""Selection accent must track the LIVE theme.

Red-before: ``ui/widgets/shelf/selection.py::_theme_manager_or_none`` imported
the long-gone ``sli_ui_toolkit.ui.theme_manager`` module → ``None`` → every
caller fell back to the LIGHT ``#0078D4`` / ``#ffffff`` pair in BOTH themes, so
a selected card in dark rendered a near-white pastel fill (``#9eccef``) that
made the light caption text unreadable. Green-after: the accent resolves the
real ThemeManager, mixing the accent toward the live ``Base`` (dark pastel in
dark, light pastel in light).
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def _palettes(qapp):
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    prev = tm.get_current_theme()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    yield tm
    try:
        tm.register_palettes({}, {})
        tm.set_theme(prev, qapp, await_ripples=False)
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass


def _set_theme(tm, qapp, name: str) -> None:
    tm.set_theme(name, qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()  # type: ignore[attr-defined]
    except Exception:
        pass
    qapp.processEvents()


def test_selection_accent_is_theme_aware(qapp, _palettes) -> None:
    from ui.widgets.shelf.selection import selection_accent_color

    tm = _palettes

    _set_theme(tm, qapp, "dark")
    dark = selection_accent_color()
    # Resolves the REAL manager (not the #0078D4/#ffffff fallback).
    assert dark.name().lower() == selection_accent_color(tm).name().lower()
    assert dark.name().lower() != "#9eccef", "dark fell back to the light pastel"
    assert dark.lightness() < 128, f"dark selection fill is too light: {dark.name()}"

    _set_theme(tm, qapp, "light")
    light = selection_accent_color()
    assert light.lightness() > 128, f"light selection fill is too dark: {light.name()}"
    assert light.name().lower() != dark.name().lower()


def test_gallery_selection_accent_is_theme_aware(qapp, _palettes) -> None:
    """The gallery's own helper (no explicit manager) tracks the theme too."""
    from tabs.image_gallery.ui.card.visuals import gallery_selection_accent

    tm = _palettes
    _set_theme(tm, qapp, "dark")
    dark = gallery_selection_accent()
    _set_theme(tm, qapp, "light")
    light = gallery_selection_accent()
    assert dark.name().lower() != light.name().lower()
    assert dark.lightness() < 128
