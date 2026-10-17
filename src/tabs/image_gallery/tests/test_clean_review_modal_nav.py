"""Clean Review (S3) declares a **trap-only modal** nav section.

S3 has no bespoke keyboard navigation yet (a later wave). What it must do now is
declare modality: while the overlay is visible, no arrow, Tab or Backtab may
reach the gallery behind the veil, and a stolen focus is pulled back. That is the
toolkit ``NavigationManager``'s modal ceiling, and this file pins the wiring:

* ``ui/clean_review/nav_section.py`` provides ``CleanReviewNavSection``
  (``modal``/``owns``/``navigate``/``focus_first``/``focus_last``/``extra_keys``)
  with idempotent ``register``/``unregister``;
* ``CleanReviewOverlay.show_for`` registers it AFTER ``show_overlay()`` (the
  overlay's own focus grab lands first);
* ``hide``/``hideEvent``/``closeEvent`` unregister it (idempotent, fail-open), so
  every close path — Esc, ✕, Cancel, move-end, card-click-to-QL and the tab
  dismiss — leaves the navigation graph;
* Esc stays native (not an arrow, not in ``extra_keys``), so it keeps closing S3.

The gallery behind the veil is represented by a plain focusable widget in the
same window: the window focus chain then really contains a target outside the
overlay, so a Tab or a programmatic ``setFocus`` is an honest leak without the
section.

Runs headless (``QT_QPA_PLATFORM=offscreen``).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager

from tabs.image_gallery.tests.test_clean_review_parity import (
    _make_overlay,
    _make_owner,
)
from tabs.image_gallery.ui.clean_review import nav_section as nav


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _open(qtbot, tmp_path):
    """A shown S3 over a window that also holds a focusable page widget."""
    owner = _make_owner(
        tmp_path,
        [str(tmp_path / f"{i}.jpg") for i in range(3)],
        folder=str(tmp_path),
    )
    overlay = _make_overlay(qtbot, owner)
    parent = overlay.parentWidget()
    page = QWidget(parent)
    page.setObjectName("stand-in-page-behind")
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    page.show()
    overlay.show_for(owner)
    QApplication.processEvents()
    return overlay, owner, page


def _press(key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> QWidget | None:
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive S3"
    QApplication.sendEvent(focused, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
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


def test_show_for_registers_a_modal_section(qtbot, tmp_path) -> None:
    """The overlay is a registered, modal nav section once it is shown.

    Falsified by: no ``nav_section`` module / no registration in ``show_for``.
    """
    overlay, _owner, _page = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    assert section is not None, "show_for must register the S3 nav section"
    assert isinstance(section, nav.CleanReviewNavSection)
    assert section.modal is True
    assert section.owns(overlay) is True
    assert any(owner is overlay for owner, _spec in NavigationManager.get_instance()._sections)
    overlay.hide()


def test_section_navigates_nothing_and_claims_no_extra_keys(qtbot, tmp_path) -> None:
    """Trap-only: no key is navigated, and Esc is never claimed as an extra key.

    Falsified by: adding Left/Right (or Esc) to ``extra_keys`` or making
    ``navigate`` consume real keys before the S3 navigation wave.
    """
    overlay, _owner, _page = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    for key in (
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Escape,
        Qt.Key.Key_Return,
    ):
        assert section.navigate(key, overlay) is False
    raw = getattr(section, "extra_keys", frozenset())  # the manager's exact read
    assert isinstance(raw, frozenset) and raw == frozenset()
    assert Qt.Key.Key_Escape not in raw
    overlay.hide()


def test_tab_never_leaves_the_overlay(qtbot, tmp_path) -> None:
    """Tab/Backtab walk the ring inside the veil and never reach the page.

    Falsified by: dropping the modal registration — the window focus chain
    contains the stand-in page widget and Tab hands it focus.
    """
    overlay, _owner, page = _open(qtbot, tmp_path)
    # Walk well past the overlay's own ring so an un-modal Tab really reaches
    # the page widget in the same window (the leak this pins).
    for _ in range(16):
        focused = _press(Qt.Key.Key_Tab)
        assert _inside(overlay, focused), f"Tab escaped the veil: {_name(focused)}"
        assert focused is not page
    for _ in range(16):
        focused = _press(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        assert _inside(overlay, focused), f"Backtab escaped the veil: {_name(focused)}"
    overlay.hide()


def test_arrows_and_a_foreign_grab_stay_inside(qtbot, tmp_path) -> None:
    """A programmatic steal is reclaimed, and arrows keep the ring in the veil.

    Falsified by: no modal registration — the steal sticks and the arrows act on
    the page widget instead of the overlay.
    """
    overlay, _owner, page = _open(qtbot, tmp_path)
    page.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle()
    assert _inside(overlay, QApplication.focusWidget()), (
        f"the steal was not reclaimed: {_name(QApplication.focusWidget())}"
    )
    for key in (
        Qt.Key.Key_Down,
        Qt.Key.Key_Up,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
    ):
        focused = _press(key)
        assert _inside(overlay, focused), f"arrow escaped the veil: {_name(focused)}"
    assert page.hasFocus() is False, "an arrow reached the page behind the veil"
    overlay.hide()


def test_escape_closes_from_the_overlay_and_from_inside_it(qtbot, tmp_path) -> None:
    """Esc is native (not an arrow, not in ``extra_keys``) from any focus state."""
    overlay, owner, _page = _open(qtbot, tmp_path)
    assert _inside(overlay, QApplication.focusWidget())
    _send_key(QApplication.focusWidget(), Qt.Key.Key_Escape)
    assert not overlay.isVisible(), "Esc must close S3 from the bare overlay"

    overlay.show_for(owner)
    QApplication.processEvents()
    _press(Qt.Key.Key_Tab)  # land on a focusable child inside the overlay
    focused = QApplication.focusWidget()
    assert _inside(overlay, focused), _name(focused)
    _send_key(focused, Qt.Key.Key_Escape)
    assert not overlay.isVisible(), "Esc must close S3 from inside the overlay"


def test_close_unregisters_and_reopen_registers_exactly_once(qtbot, tmp_path) -> None:
    """Every close drops the section; a reopen lands exactly one registration."""
    overlay, owner, _page = _open(qtbot, tmp_path)
    manager = NavigationManager.get_instance()
    assert nav.section_of(overlay) is not None
    assert sum(1 for o, _s in manager._sections if o is overlay) == 1

    overlay.hide()
    QApplication.processEvents()
    assert nav.section_of(overlay) is None, "the close path must unregister S3"
    assert not any(o is overlay for o, _s in manager._sections)

    overlay.show_for(owner)
    QApplication.processEvents()
    assert sum(1 for o, _s in manager._sections if o is overlay) == 1
    section = nav.section_of(overlay)
    assert section is not None and section.modal is True
    overlay.hide()
