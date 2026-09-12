"""ThemedDialog paints its own surface from the ``dialog.background`` token.

QSS is retired (dialog-surface phase of plan_qss_retirement.md): top-level
QDialog QSS rules are gone, so a bare dialog would paint the QPalette
Window role (dark ``#1e1e1e`` — near-black against the ``#2b2b2b`` dialog
surface token). ``ThemedDialog.paintEvent`` fills the surface explicitly and
re-tints on ``theme_changed`` — the same explicit-paint pattern as the
toolkit ``_SurfaceWidget`` / ``IconListWidget`` (see
``sli-ui-toolkit/tests/test_dialog_shell_surface.py``).
"""

from __future__ import annotations

import pytest

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from shared_toolkit.ui.themed_dialog import ThemedDialog
from sli_ui_toolkit.managers import ThemeManager


class _SurfaceProbeDialog(ThemedDialog):
    def __init__(self):
        super().__init__()
        self.setObjectName("SurfaceProbeDialog")
        self.resize(240, 160)
        self.mark_theme_ui_ready()


@pytest.fixture
def themed(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("dark", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm
    tm.set_theme("dark", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def _center_pixel(widget) -> str:
    img = widget.grab().toImage()
    return img.pixelColor(img.width() // 2, img.height() // 2).name()


def test_themed_dialog_surface_paints_dialog_background_token(qapp, qtbot, themed):
    dlg = _SurfaceProbeDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    qapp.processEvents()
    assert _center_pixel(dlg) == "#2b2b2b"


def test_themed_dialog_surface_survives_show_polish(qapp, qtbot, themed):
    """QStyle::polish at show() resets widget palettes — the painted
    surface must not fall back to the near-black Window role."""
    dlg = _SurfaceProbeDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    qapp.processEvents()
    dlg.style().unpolish(dlg)
    dlg.style().polish(dlg)
    qapp.processEvents()
    assert _center_pixel(dlg) == "#2b2b2b"


def test_themed_dialog_surface_re_tints_on_theme_switch(qapp, qtbot, themed):
    dlg = _SurfaceProbeDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    qapp.processEvents()
    assert _center_pixel(dlg) == "#2b2b2b"

    themed.set_theme("light", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    qapp.processEvents()
    assert _center_pixel(dlg) == "#ffffff"

    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    qapp.processEvents()
    assert _center_pixel(dlg) == "#2b2b2b"