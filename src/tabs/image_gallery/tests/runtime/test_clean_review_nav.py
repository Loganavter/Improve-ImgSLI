"""Clean Review (S3) keyboard navigation — real rows over the real overlay.

The overlay is a modal ``ToolbarRowsSection`` (``ui/clean_review/nav_section.py``)
over the three rows it already has, top to bottom: header (✕), item strip
(per-item ``↩ Restore`` buttons + the informational ``+N more`` tile) and the
action bar (Restore all / Cancel / Move). ``↓``/``↑`` cross rows, ``←``/``→``
step inside a row, Enter/Space activate the focused toolkit ``Button``, the
vertical edges wrap inside the veil, and closing returns the ring to the
opener.

Every test runs over the real ``CleanReviewOverlay`` and the real
``NavigationManager``, offscreen; keys go through ``QApplication.sendEvent`` to
the focused widget so the whole manager → section → widget path is exercised.
Each test carries a ``Falsified by:`` note naming the code whose removal turns
it red — these are regression pins, not implementation restatements.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.widgets import Button

from tabs.image_gallery.tests.test_clean_review_parity import (
    _make_owner,
    _make_overlay,
)
from tabs.image_gallery.ui.clean_review import nav_section as nav


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    """Undo the app-wide input-modality flip every injected key causes."""
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _open(qtbot, tmp_path, n: int = 3):
    """A shown S3 with *n* rejected items."""
    owner = _make_owner(
        tmp_path,
        [str(tmp_path / f"{i}.jpg") for i in range(n)],
        folder=str(tmp_path),
    )
    overlay = _make_overlay(qtbot, owner)
    parent = overlay.parentWidget()
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    overlay.show_for(owner)
    QApplication.processEvents()
    return overlay, owner


def _press(key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> QWidget | None:
    """Deliver a real key press to the focused widget (manager path included)."""
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive S3"
    QApplication.sendEvent(focused, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    QApplication.processEvents()
    return QApplication.focusWidget()


def _name(widget) -> str:
    return str(widget.objectName()) if widget is not None else "<none>"


def _restore_buttons(overlay) -> list[Button]:
    strip = overlay._strip_row
    assert strip is not None, "S3 must expose the current strip row"
    buttons = [
        w
        for w in strip.findChildren(Button)
        if str(w.objectName()) == "clean_review_restore"
    ]
    return sorted(buttons, key=lambda w: w.mapToGlobal(w.rect().center()).x())


def _inside(overlay, widget) -> bool:
    return widget is not None and (widget is overlay or overlay.isAncestorOf(widget))


def _in_row(row, widget) -> bool:
    try:
        return bool(row is not None and widget is not None and (row is widget or row.isAncestorOf(widget)))
    except Exception:
        return False


def test_section_is_the_toolkit_row_section_with_every_control_owned(qtbot, tmp_path):
    """All three rows are registered and every Button belongs to one of them.

    Falsified by: reverting ``nav_section.rows`` to a single trap, dropping the
    strip/action row attributes, or leaving a Button outside the row
    containers (it would then be click-only again).
    """
    overlay, _owner = _open(qtbot, tmp_path, n=9)  # 9 > cap → +N tile exists
    section = nav.section_of(overlay)
    assert section is not None
    assert isinstance(section, ToolbarRowsSection), "rows must be the toolkit section"
    assert section.modal is True

    registered = nav.rows(overlay)
    assert registered == [overlay._close_btn, overlay._strip_row, overlay._action_bar]
    assert all(row is not None for row in registered), registered

    controls = overlay.findChildren(Button)
    assert controls, "the real overlay must expose its buttons"
    for control in controls:
        assert section.owns(control), f"{_name(control)} is not owned by the section"
        assert any(_in_row(row, control) for row in registered), (
            f"{_name(control)} is not inside any navigable row"
        )

    assert section.owns(overlay._close_btn)
    for key in ("_restore_all_btn", "_cancel_btn", "_move_btn"):
        assert section.owns(getattr(overlay, key)), key
    restores = _restore_buttons(overlay)
    assert len(restores) == 8  # FILMSTRIP_MAX_CELLS
    for button in restores:
        assert section.owns(button)

    more = overlay.findChild(QWidget, "clean_review_filmstrip_more")
    assert more is not None, "9 items must build the +N tile"
    assert section.owns(more), "the more-tile must join the strip's row model"
    overlay.hide()


def test_down_walks_header_then_strip_then_actions_and_wraps(qtbot, tmp_path):
    """Down visits header → strip → action bar; the edges stay inside S3.

    Falsified by: returning the trap section (no rows), a rows provider that
    skips the strip/action bar, or a boundary that yields to the page behind.
    """
    overlay, _owner = _open(qtbot, tmp_path)
    assert QApplication.focusWidget() is overlay._close_btn, (
        f"registering the section must enter on the header, got {_name(QApplication.focusWidget())}"
    )

    focused = _press(Qt.Key.Key_Down)
    assert _in_row(overlay._strip_row, focused), _name(focused)
    focused = _press(Qt.Key.Key_Down)
    assert _in_row(overlay._action_bar, focused), _name(focused)

    focused = _press(Qt.Key.Key_Down)  # bottom edge — wraps, never leaks
    assert QApplication.focusWidget() is overlay._close_btn, _name(focused)
    focused = _press(Qt.Key.Key_Up)  # top edge — wraps again
    assert _in_row(overlay._action_bar, focused), _name(focused)
    overlay.hide()


def test_left_right_walk_the_strip_row(qtbot, tmp_path):
    """Left/Right step between the per-item Restore buttons of the strip.

    Falsified by: not re-delivering horizontal arrows to the section
    (``CleanReviewOverlay.keyPressEvent``) or an extra_keys-only design that
    never reaches ``ToolbarRowsSection.navigate``.
    """
    overlay, _owner = _open(qtbot, tmp_path, n=4)
    restores = _restore_buttons(overlay)
    assert len(restores) == 4
    restores[0].setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert QApplication.focusWidget() is restores[0]

    focused = _press(Qt.Key.Key_Right)
    assert focused is restores[1], _name(focused)
    focused = _press(Qt.Key.Key_Right)
    assert focused is restores[2], _name(focused)
    focused = _press(Qt.Key.Key_Left)
    assert focused is restores[1], _name(focused)
    overlay.hide()


def test_enter_on_close_activates_it_and_returns_focus_to_the_opener(qtbot, tmp_path):
    """Enter on ✕ closes S3 and the ring goes back to the opener widget.

    Falsified by: a section that claims Return (the Button never activates), a
    close path that does not unregister, or ``unregister`` forgetting
    ``restore_opener_focus``.
    """
    overlay, owner = _open(qtbot, tmp_path)
    parent = overlay.parentWidget()
    opener = QWidget(parent)
    opener.setObjectName("s3-opener")
    opener.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    opener.show()
    opener.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()

    overlay.hide()
    QApplication.processEvents()
    overlay.show_for(owner)  # remembers ``opener`` (it holds the ring now)
    QApplication.processEvents()
    assert QApplication.focusWidget() is overlay._close_btn

    _press(Qt.Key.Key_Return)
    assert not overlay.isVisible(), "Enter on ✕ must close S3"
    assert nav.section_of(overlay) is None, "the close path must unregister the section"
    assert QApplication.focusWidget() is opener, (
        f"focus must return to the opener, got {_name(QApplication.focusWidget())}"
    )


def test_space_on_a_restore_button_restores_and_keeps_the_model_current(qtbot, tmp_path):
    """Space activates a per-item Restore; the rebuilt strip is the live row.

    Falsified by: not letting the toolkit Button activate on Space, or caching
    the row list (the rebuilt strip would still be the deleted one).
    """
    overlay, owner = _open(qtbot, tmp_path, n=3)
    old_strip = overlay._strip_row
    assert old_strip is not None
    restores = _restore_buttons(overlay)
    restores[1].setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()

    _press(Qt.Key.Key_Space)
    QApplication.processEvents()

    rejected = [it for it in owner.state.items if bool(getattr(it, "rejected", False))]
    assert len(rejected) == 2, "Space on ↩ Restore must restore exactly that item"
    assert overlay.isVisible(), "restoring one item must not close S3"

    assert overlay._strip_row is not None and overlay._strip_row is not old_strip, (
        "populate must build a fresh strip row"
    )
    assert nav.rows(overlay)[1] is overlay._strip_row, "rows must be re-derived"
    section = nav.section_of(overlay)
    assert section is not None
    assert section.owns(overlay._strip_row)
    for button in _restore_buttons(overlay):
        assert section.owns(button), "the rebuilt Restore buttons must be owned"
    focused = QApplication.focusWidget()
    assert _inside(overlay, focused), f"the ring left S3 after a rebuild: {_name(focused)}"
    overlay.hide()


def test_a_new_item_set_replaces_the_row_model(qtbot, tmp_path):
    """Populate with a new item set re-derives rows instead of caching them.

    Falsified by: storing the strip row once in ``__init__``/``register`` — the
    section would keep navigating the deleted strip after the rebuild.
    """
    overlay, owner = _open(qtbot, tmp_path, n=2)
    old_strip = overlay._strip_row
    owner.state.items.append(
        SimpleNamespace(
            rejected=True,
            path=str(tmp_path / "late.jpg"),
            name="late.jpg",
            thumbnail=None,
            provenance_series_id="series_1",
        )
    )
    overlay._populate(owner)
    QApplication.processEvents()

    section = nav.section_of(overlay)
    assert section is not None
    assert overlay._strip_row is not old_strip
    assert nav.rows(overlay)[1] is overlay._strip_row
    assert len(_restore_buttons(overlay)) == 3
    for button in _restore_buttons(overlay):
        assert section.owns(button)
    overlay.hide()


def test_boundary_down_never_reaches_a_host_section_behind_the_veil(qtbot, tmp_path):
    """A host section on the page behind S3 receives no arrow while it is up.

    Falsified by: dropping ``modal`` (the manager then hands the edge arrow to
    the page section) or a boundary that returns/forwards to a neighbour.
    """
    overlay, _owner = _open(qtbot, tmp_path)
    parent = overlay.parentWidget()
    page = QWidget(parent)
    page.setObjectName("stand-in-page-behind")
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    page.show()

    calls: list[int] = []

    class _HostSection:
        modal = False
        extra_keys = frozenset()

        def owns(self, widget):
            return widget is page

        def navigate(self, key, widget):
            calls.append(key)
            return True

        def focus_first(self, ref_x=None, *, reason=None):
            page.setFocus(reason or Qt.FocusReason.OtherFocusReason)
            return True

        def focus_last(self, ref_x=None, *, reason=None):
            return self.focus_first(ref_x, reason=reason)

    manager = NavigationManager.get_instance()
    host = _HostSection()
    manager.register(page, host)
    try:
        overlay.show_for(overlay._owner)  # re-register S3 above the host
        QApplication.processEvents()
        # The rows really move (Down enters the strip), then keep pressing
        # Down past the bottom edge.
        focused = _press(Qt.Key.Key_Down)
        assert _in_row(overlay._strip_row, focused), (
            f"Down did not enter the strip: {_name(focused)}"
        )
        for _ in range(8):
            _press(Qt.Key.Key_Down)
            focused = QApplication.focusWidget()
            assert _inside(overlay, focused), f"Down escaped the veil: {_name(focused)}"
            assert focused is not page
        assert calls == [], "the host section behind the veil received an arrow"
        assert page.hasFocus() is False
    finally:
        overlay.hide()
        manager.unregister(page)
