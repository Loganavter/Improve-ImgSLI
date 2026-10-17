"""Quick Look declares a **modal** nav section — the keyboard cannot leave the veil.

The panel owns the gallery window's keyboard while it is visible: the toolkit
``NavigationManager`` reads ``QuickLookNavSection.modal`` (``True``) and then

* routes every arrow key, the section's ``extra_keys`` and Tab/Backtab into the
  panel (``navigation_manager.py`` ``eventFilter`` modal-ceiling block);
* consumes an arrow at the panel's edge instead of yielding to a section behind
  the veil (the old panel-local Up/Down edge-consume is gone — it lived in
  ``QuickLookNavSection.navigate`` lines 341-345 and was the workaround this
  test file replaces);
* pulls focus back inside the panel when a foreign widget steals it
  (``_reclaim_modal_focus``).

The grid behind the veil is represented by a plain stand-in focusable widget in
the same window plus a ``_NeighbourSection`` registered *before* the panel: the
window focus chain then really contains a widget outside the overlay, so Tab and
a programmatic ``setFocus`` are honest leaks on an un-modal panel.

Runs offscreen (no Xvfb): the real ``QuickLookOverlay`` + the real
``NavigationManager``, keys delivered through ``QApplication.sendEvent`` to the
focused widget, so the whole manager → section → widget path is exercised.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.tests.test_quicklook_strip import (
    _make_overlay,
    _real_png,
    _show,
)
from tabs.image_gallery.ui.quick_look import nav_section as nav


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    """Undo the app-wide input-modality flip every injected key causes."""
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _series(tmp_path, n: int = 4) -> list[GalleryItem]:
    paths = [_real_png(tmp_path, f"n{i}.png") for i in range(n)]
    return [GalleryItem(path=p, mtime_ns=i + 1, rank=i + 1) for i, p in enumerate(paths)]


class _NeighbourSection:
    """A stand-in page section registered before the panel (the grid behind)."""

    def __init__(self, widget) -> None:
        self._widget = widget

    def owns(self, widget) -> bool:
        return widget is self._widget

    def navigate(self, key, widget) -> bool:
        return False

    def focus_first(self, ref_x=None, *, reason) -> bool:
        self._widget.setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason) -> bool:
        self._widget.setFocus(reason)
        return True


def _open_with_page(qtbot, tmp_path, n: int = 4, current: int = 2):
    """A shown panel over a window that also holds a focusable page widget.

    The stand-in is a real, focusable widget in the SAME window as the overlay —
    the window focus chain therefore contains a target outside the veil, which
    is what makes a Tab/``setFocus`` leak observable offscreen. A stand-in
    section is registered before the panel so a yielded arrow has a neighbour
    to walk onto (the grid-behind-the-veil shape).
    """
    items = _series(tmp_path, n)
    overlay = _make_overlay(qtbot)
    parent = overlay.parentWidget()
    page = QWidget(parent)
    page.setObjectName("stand-in-page-behind")
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    manager = NavigationManager.get_instance()
    manager.register(page, _NeighbourSection(page))
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    _show(overlay, items[current], items)
    QApplication.processEvents()
    return overlay, items, page


def _press(key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> QWidget | None:
    """Deliver a real key press to the focused widget (manager path included)."""
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive the panel"
    QApplication.sendEvent(
        focused, QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    )
    QApplication.processEvents()
    return QApplication.focusWidget()


def _send_key(widget, key: Qt.Key) -> None:
    QApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    )
    QApplication.processEvents()


def _settle() -> None:
    for _ in range(4):
        QApplication.processEvents()


def _name(widget) -> str:
    return str(widget.objectName()) if widget is not None else "<none>"


def _inside(overlay, widget) -> bool:
    return widget is not None and (widget is overlay or overlay.isAncestorOf(widget))


def test_the_panel_declares_modal(qtbot, tmp_path) -> None:
    """The section reads ``modal is True`` — the toolkit is told about the veil.

    Falsified by: dropping the ``modal`` property from ``QuickLookNavSection``.
    """
    overlay, _items, _page = _open_with_page(qtbot, tmp_path)
    section = nav.section_of(overlay)
    assert section is not None
    assert section.modal is True
    overlay.hide()


def test_tab_never_leaves_the_overlay(qtbot, tmp_path) -> None:
    """Tab/Backtab walk the ring inside the veil and never reach the page.

    Falsified by: removing the ``modal`` declaration — the window focus chain
    then contains the stand-in page widget and Tab hands it focus.
    """
    overlay, _items, page = _open_with_page(qtbot, tmp_path)
    # The overlay's own ring is ~10 widgets long (strip thumbs + the action bar,
    # ✕, the ‹/› circles, the scroll area): walk well past its edge so an
    # un-modal Tab really reaches the page widget in the same window.
    for _ in range(16):
        focused = _press(Qt.Key.Key_Tab)
        assert _inside(overlay, focused), f"Tab escaped the veil: {_name(focused)}"
        assert focused is not page
    for _ in range(16):
        focused = _press(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        assert _inside(overlay, focused), f"Backtab escaped the veil: {_name(focused)}"
    overlay.hide()


def test_a_foreign_focus_grab_is_pulled_back(qtbot, tmp_path) -> None:
    """A programmatic steal to a widget behind the veil is reclaimed.

    ``OtherFocusReason`` is exactly the programmatic steal the manager's
    ``_reclaim_modal_focus`` is written for (a ``Mouse``/``Popup`` reason is the
    panel's own grab). Falsified by: no ``modal`` declaration — nothing pulls
    focus back and it stays on the page widget.
    """
    overlay, _items, page = _open_with_page(qtbot, tmp_path)
    page.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle()
    focused = QApplication.focusWidget()
    assert _inside(overlay, focused), f"the steal was not reclaimed: {_name(focused)}"
    overlay.hide()


def test_arrows_after_a_steal_stay_inside_and_never_move_the_page(qtbot, tmp_path) -> None:
    """With focus recovered, every arrow keeps the ring inside the panel.

    Falsified by: removing the ``modal`` declaration — after the steal focus
    stays on the page widget and an arrow just re-delivers there.
    """
    overlay, _items, page = _open_with_page(qtbot, tmp_path)
    page.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle()
    assert _inside(overlay, QApplication.focusWidget())
    for key in (
        Qt.Key.Key_Down,
        Qt.Key.Key_Down,
        Qt.Key.Key_Up,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
    ):
        focused = _press(key)
        assert _inside(overlay, focused), f"arrow escaped the veil: {_name(focused)}"
    assert page.hasFocus() is False, "an arrow reached the page behind the veil"
    overlay.hide()


def test_arrows_at_the_panel_edge_never_hand_off_to_the_page(qtbot, tmp_path) -> None:
    """Up on the top row / Down on the bottom row keep the ring in the panel.

    The panel-local edge-consume was deleted; the manager's modal edge now owns
    this. Falsified by: removing the ``modal`` declaration — the toolkit rows
    yield Up/Down past the last row straight to the stand-in neighbour.
    """
    overlay, _items, page = _open_with_page(qtbot, tmp_path)
    focused = _press(Qt.Key.Key_Up)
    assert _inside(overlay, focused), _name(focused)
    _press(Qt.Key.Key_Down)  # into the action row
    _press(Qt.Key.Key_Down)  # at the bottom edge
    assert _inside(overlay, QApplication.focusWidget()), "Down left the panel"
    assert page.hasFocus() is False
    overlay.hide()


def test_escape_with_focus_inside_closes_the_panel(qtbot, tmp_path) -> None:
    """Esc is not an arrow and not in ``extra_keys`` — native close still works.

    Regression shield for the modal declaration: if the manager swallowed Esc
    the panel would become unclosable from the keyboard.
    """
    overlay, _items, _page = _open_with_page(qtbot, tmp_path)
    focused = QApplication.focusWidget()
    assert _inside(overlay, focused)
    _send_key(focused, Qt.Key.Key_Escape)
    assert not overlay.isVisible(), "Esc must close the panel from inside"
