"""Selection HUD background regression tests.

The HUD flyout ("N selected" capsule) once used a near-transparent white
tint as its BaseFlyout background brush — but set_background_brush REPLACES
the panel fill instead of layering over it, so the capsule rendered
transparent with only its drop shadow visible. The brush must stay opaque.
"""

from __future__ import annotations

import pytest

from tabs.image_gallery.ui.selection_hud import SelectionHudController


@pytest.fixture
def hud(qtbot):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    controller = SelectionHudController(parent, on_clear=None, on_carry=None)
    qtbot.addWidget(controller.flyout)
    return controller


def test_hud_background_brush_is_opaque(hud: SelectionHudController) -> None:
    """HUD panel fill must be fully opaque (no see-through capsule)."""
    hud.update(2)
    brush = hud.flyout.background_brush()
    assert brush is not None
    stops = brush.gradient().stops()
    assert stops, "HUD background must be a gradient brush"
    for pos, color in stops:
        assert color.alpha() == 255, f"transparent stop at {pos}: {color.getRgb()}"


def test_hud_shows_on_selection(hud: SelectionHudController, qtbot) -> None:
    """Sanity: HUD shows for n>0, hides for 0 (unchanged behavior)."""
    hud._parent.show()
    qtbot.waitExposed(hud._parent)
    hud.update(3)
    assert hud.flyout.isVisible()
    hud.update(0)
    assert not hud.flyout.isVisible()
