"""Runtime parity gate: a surface must visibly recolour across a theme flip.

Complements the static contract (`tests/contracts/test_theme_recolor_contracts.py`):
the contract catches the *shape* (eager/cached theme state), this catches the
*behaviour* (a surface that did not repaint). Origin: the session-picker shelf
children lagged one theme (inv-theme-recolor-offbyone-2026-10-14).
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from sli_ui_toolkit.theme import ThemeManager


def assert_recolors_on_theme_flip(
    qapp: QApplication,
    target: QWidget,
    *,
    from_theme: str = "light",
    to_theme: str = "dark",
) -> None:
    """Assert ``target``'s rendered pixels change across a live theme switch.

    ``grab()`` reads the actual rendered pixmap (not the compositor), so a
    surface that silently kept the previous theme fails here.
    """
    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme(from_theme, qapp, await_ripples=False)
    qapp.processEvents()
    before = target.grab().toImage()

    tm.set_theme(to_theme, qapp, await_ripples=False)
    qapp.processEvents()
    after = target.grab().toImage()

    # Leave global theme state clean for the next test.
    tm.set_theme(from_theme, qapp, await_ripples=False)
    qapp.processEvents()

    assert before != after, (
        f"{type(target).__name__} did not recolour on "
        f"{from_theme}->{to_theme} (stale theme state)"
    )
