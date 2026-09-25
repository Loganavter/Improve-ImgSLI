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


def test_hud_notify_replaces_buttons_then_restores(hud: SelectionHudController, qtbot) -> None:
    """notify() swaps the action row for a message; timer restores it."""
    hud._parent.show()
    qtbot.waitExposed(hud._parent)
    hud.update(1)
    assert hud._label.text() == "1 selected"

    hud.notify("Rejected foo.png", timeout_ms=50)
    assert hud._label.text() == "Rejected foo.png"
    for btn in (hud._clear_btn, hud._find_similar_btn, hud._carry_btn):
        assert not btn.isVisibleTo(hud.flyout)

    # Stale timer ignored; current token restores.
    hud._end_notify(hud._notify_token - 1)
    assert hud._label.text() == "Rejected foo.png"
    hud._end_notify(hud._notify_token)
    assert hud._label.text() == "1 selected"
    for btn in (hud._clear_btn, hud._find_similar_btn, hud._carry_btn):
        assert btn.isVisibleTo(hud.flyout)


def test_capsule_suppression_roundtrip() -> None:
    """Post-action window suppresses the hover capsule, then expires."""
    from types import SimpleNamespace

    from tabs.image_gallery.ui.card.hover import _capsule_suppressed, _suppress_capsule

    owner = SimpleNamespace()
    card = SimpleNamespace()
    assert _capsule_suppressed(owner, card) is False
    _suppress_capsule(owner, card, ms=50)
    assert _capsule_suppressed(owner, card) is True
    assert _capsule_suppressed(None, card) is True
    import time

    deadline = time.monotonic() + 2.0
    while _capsule_suppressed(owner, card) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _capsule_suppressed(owner, card) is False
