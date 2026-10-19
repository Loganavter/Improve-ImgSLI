"""Keyboard navigation for the unified list picker's two list panels.

Audit rank 1 (2026-10-19): the picker is a plain ``QWidget``, not a toolkit
``BaseFlyout``, so it registered NO navigation section — every row Button and
both panels were arrow-unreachable (the keyboard cursor stayed on the opener),
and the ``+/-`` rating steppers were ``NoFocus`` and therefore click-only.

What the section must do (``ui/widgets/unified_list_picker/nav.py``):

* ``owns`` claims every live interactive cell — row Buttons AND their nested
  ``+/-`` steppers (both panels), never the panels/host;
* Down/Up walk rows inside the FOCUSED panel;
* Left/Right walk the visual band in x order, which carries focus across the
  panel gap; band/panel edges decline (``False``) instead of wrapping, so
  ``NavigationManager`` hands the key to the neighbouring section;
* Enter/Space activate the focused control (toolkit ``Button`` natively);
* the section lives only while the picker is visible — hide unregisters it.

Falsification (RED against the pre-change tree): before the change the picker
registered no section at all, so ``_section(picker)`` raises
("the picker registered no navigation section"), ownership is empty and every
arrow assertion below is unreachable. The stepper test pins the focus-policy
decision: pre-change ``btn_plus.focusPolicy() == NoFocus`` and the cell is not
owned, so it fails before the arrows move.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager
from ui.widgets.rating_item import RatingListItem
from ui.widgets.unified_list_picker import UnifiedListPicker


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _HostSection:
    """The section above the picker (a tab toolbar stand-in), registered first.

    Its only job here is to prove the picker's top-row Up DECLINES and the
    manager hands the key to the neighbouring section instead of wrapping.
    """

    def __init__(self, button: QWidget) -> None:
        self._button = button

    @property
    def button(self) -> QWidget:
        """The control this section owns (the picker's vertical neighbour)."""
        return self._button

    def owns(self, widget) -> bool:  # noqa: ANN001
        return widget is self._button

    def navigate(self, key: int, widget) -> bool:  # noqa: ANN001
        return False

    def focus_first(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason) -> bool:  # noqa: ANN001
        self._button.setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason) -> bool:  # noqa: ANN001
        self._button.setFocus(reason)
        return True


def _pump(qapp, rounds: int = 3) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def _make_picker(
    qapp,
    *,
    register_host_section: bool = False,
    left_items: list[str] | None = None,
    right_items: list[str] | None = None,
):
    host = QWidget()
    host.resize(900, 700)
    left_anchor = QWidget(host)
    left_anchor.setGeometry(50, 200, 220, 34)
    right_anchor = QWidget(host)
    right_anchor.setGeometry(450, 200, 220, 34)
    host_anchor = QWidget(host)
    host_anchor.setGeometry(50, 60, 220, 34)
    host.show()
    _pump(qapp)

    picker = UnifiedListPicker.create_double_list(
        host,
        left_anchor,
        right_anchor,
        left_items=left_items or ["Alpha", "Beta", "Gamma", "Delta"],
        right_items=right_items or ["One", "Two", "Three"],
    )
    picker.set_list_anchors(left_anchor, right_anchor)

    host_section = None
    if register_host_section:
        # Registered BEFORE the picker shows, so it sits above it in the
        # registry (registration order is the manager's vertical order).
        host_section = _HostSection(host_anchor)
        NavigationManager.get_instance().register(host_anchor, host_section)

    picker.showAsSingle(1, left_anchor)
    _pump(qapp)
    picker.switchToDoubleMode()
    _pump(qapp, rounds=5)
    return host, picker, left_anchor, host_section


def _teardown(qapp, host, picker, host_section=None) -> None:
    manager = NavigationManager.get_instance()
    try:
        picker.hide()
    except RuntimeError:
        pass
    if host_section is not None:
        manager.unregister(host_section.button)
    manager.unregister(picker)
    picker.deleteLater()
    host.close()
    host.deleteLater()
    _pump(qapp)


def _section(picker):
    manager = NavigationManager.get_instance()
    for owner, spec in list(manager._sections):
        if owner is picker:
            return spec
    raise AssertionError("the picker registered no navigation section")


def _rows(panel) -> list[RatingListItem]:
    return [
        widget
        for widget in panel.content_widget.findChildren(RatingListItem)
        if widget.isVisible()
    ]


def _kbd_focus(widget: QWidget, qapp) -> None:
    """Grant keyboard-modality focus (modality follows the last input device)."""
    QTest.keyClick(widget, Qt.Key.Key_F1)
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    _pump(qapp)


def _focused(panel) -> QWidget:
    focused = QApplication.focusWidget()
    assert focused is not None, "navigation left no Qt focus widget"
    assert panel.isAncestorOf(focused), (
        f"focus escaped the panel: {type(focused).__name__}"
    )
    return focused


def test_picker_registers_a_section_that_owns_every_interactive_cell(qapp):
    host, picker, _anchor, _host_section = _make_picker(qapp)
    try:
        spec = _section(picker)

        for panel in (picker.panel_left, picker.panel_right):
            rows = _rows(panel)
            assert rows, "the panel must have live rows to navigate"
            for row in rows:
                assert spec.owns(row), (
                    "every row Button must be owned by the picker section"
                )
                assert row.focusPolicy() == Qt.FocusPolicy.StrongFocus
                for stepper in (row.btn_minus, row.btn_plus):
                    assert stepper.focusPolicy() == Qt.FocusPolicy.StrongFocus, (
                        "the +/- rating steppers are real actions: StrongFocus so "
                        "Enter/Space activate them from the navigation cursor"
                    )
                    assert spec.owns(stepper), (
                        "a StrongFocus +/- stepper the section does not own is an "
                        "orphan: the keyboard cursor can never reach it"
                    )

        # No unowned interactive descendant: ownership is not just the rows.
        orphans = [
            (type(widget).__name__, widget.objectName())
            for panel in (picker.panel_left, picker.panel_right)
            for widget in panel.content_widget.findChildren(QWidget)
            if widget.focusPolicy() == Qt.FocusPolicy.StrongFocus
            and widget.isVisible()
            and widget.isEnabled()
            and not spec.owns(widget)
        ]
        assert not orphans, f"unowned interactive cells: {orphans}"
    finally:
        _teardown(qapp, host, picker)


def test_down_up_walk_rows_inside_the_focused_panel(qapp):
    host, picker, _anchor, _host_section = _make_picker(qapp)
    try:
        left_rows = _rows(picker.panel_left)
        _kbd_focus(left_rows[0], qapp)

        QTest.keyClick(left_rows[0], Qt.Key.Key_Down)
        assert _focused(picker.panel_left) is left_rows[1]
        QTest.keyClick(left_rows[1], Qt.Key.Key_Down)
        assert _focused(picker.panel_left) is left_rows[2]
        QTest.keyClick(left_rows[2], Qt.Key.Key_Up)
        assert _focused(picker.panel_left) is left_rows[1]

        # Same walk in the right panel, without leaving it.
        right_rows = _rows(picker.panel_right)
        _kbd_focus(right_rows[0], qapp)
        QTest.keyClick(right_rows[0], Qt.Key.Key_Down)
        assert _focused(picker.panel_right) is right_rows[1]
        QTest.keyClick(right_rows[1], Qt.Key.Key_Up)
        assert _focused(picker.panel_right) is right_rows[0]
    finally:
        _teardown(qapp, host, picker)


def test_left_right_walk_crosses_the_panel_gap_without_wrapping(qapp):
    """Left/Right are spatial: row -> its steppers -> the other panel.

    A visual band is one row of BOTH panels (x-sorted), so the right edge of
    the left panel's band is immediately followed by the right panel's row —
    the arrow carries focus across the gap in the same band.
    """
    host, picker, _anchor, _host_section = _make_picker(qapp)
    try:
        left_row = _rows(picker.panel_left)[0]
        right_row = _rows(picker.panel_right)[0]
        _kbd_focus(left_row, qapp)

        QTest.keyClick(left_row, Qt.Key.Key_Right)
        assert QApplication.focusWidget() is left_row.btn_minus
        QTest.keyClick(left_row.btn_minus, Qt.Key.Key_Right)
        assert QApplication.focusWidget() is left_row.btn_plus
        QTest.keyClick(left_row.btn_plus, Qt.Key.Key_Right)
        assert _focused(picker.panel_right) is right_row, (
            "Right from the left panel's band edge must carry focus into the "
            "right panel at the same visual row"
        )

        QTest.keyClick(right_row, Qt.Key.Key_Left)
        assert _focused(picker.panel_left) is left_row.btn_plus, (
            "Left from the right panel row must cross back into the left panel"
        )

        # Right edge of the whole band: declines, never wraps to the next row.
        _kbd_focus(right_row.btn_plus, qapp)
        QTest.keyClick(right_row.btn_plus, Qt.Key.Key_Right)
        assert QApplication.focusWidget() is right_row.btn_plus, (
            "the band's right edge must decline instead of wrapping"
        )

        # Left edge of the whole band: declines, never wraps either.
        _kbd_focus(left_row, qapp)
        QTest.keyClick(left_row, Qt.Key.Key_Left)
        assert QApplication.focusWidget() is left_row, (
            "the band's left edge must decline instead of wrapping"
        )
    finally:
        _teardown(qapp, host, picker)


def test_enter_and_space_activate_the_focused_control(qapp):
    host, picker, _anchor, _host_section = _make_picker(qapp)
    try:
        left_rows = _rows(picker.panel_left)
        # The activation path is only meaningful for cells the navigation
        # cursor can actually reach (pre-change: no section at all).
        assert _section(picker).owns(left_rows[1])
        chosen: list[tuple[int, int]] = []
        picker.item_chosen.connect(lambda list_num, index: chosen.append((list_num, index)))

        _kbd_focus(left_rows[1], qapp)
        QTest.keyClick(left_rows[1], Qt.Key.Key_Return)
        _pump(qapp)
        assert chosen == [(1, 1)], "Enter on a row must choose that row's item"
        assert not picker.isVisible(), "choosing an item closes the picker"
        assert getattr(picker, "_nav_section", None) is None, (
            "the closed picker must drop its navigation section"
        )

        # Re-open: the section must come back, and Space must activate too.
        picker.showAsSingle(1, _anchor)
        _pump(qapp)
        picker.switchToDoubleMode()
        _pump(qapp, rounds=5)
        left_row = _rows(picker.panel_left)[0]

        _kbd_focus(left_row.btn_plus, qapp)
        QTest.keyClick(left_row.btn_plus, Qt.Key.Key_Space)
        _pump(qapp)
        assert picker.store.doc.list1[0].rating == 1, (
            "Space on the focused + stepper must step the rating"
        )

        _kbd_focus(left_row.btn_minus, qapp)
        QTest.keyClick(left_row.btn_minus, Qt.Key.Key_Return)
        _pump(qapp)
        assert picker.store.doc.list1[0].rating == 0, (
            "Enter on the focused - stepper must step the rating back"
        )
        assert picker.isVisible(), "stepping a rating must not choose/close the row"
    finally:
        _teardown(qapp, host, picker)


def test_edges_decline_to_the_host_section(qapp):
    host, picker, _anchor, host_section = _make_picker(
        qapp, register_host_section=True
    )
    try:
        assert host_section is not None
        left_rows = _rows(picker.panel_left)

        # Up at the picker's top row declines to the section registered above
        # it (the tab toolbar stand-in) instead of being consumed.
        _kbd_focus(left_rows[0], qapp)
        QTest.keyClick(left_rows[0], Qt.Key.Key_Up)
        _pump(qapp)
        assert QApplication.focusWidget() is host_section.button, (
            "Up at the top row must hand focus back to the host section"
        )

        # Down at the bottom row declines too: nothing below the picker, so
        # the key is consumed by the manager and focus must NOT wrap.
        bottom = left_rows[-1]
        _kbd_focus(bottom, qapp)
        QTest.keyClick(bottom, Qt.Key.Key_Down)
        assert QApplication.focusWidget() is bottom, (
            "Down at the last row must not wrap around to the first row"
        )
    finally:
        _teardown(qapp, host, picker, host_section)


def test_hiding_the_picker_unregisters_its_section(qapp):
    host, picker, _anchor, _host_section = _make_picker(qapp)
    try:
        assert _section(picker) is not None
        picker.hide()
        _pump(qapp)

        manager = NavigationManager.get_instance()
        assert all(owner is not picker for owner, _spec in manager._sections), (
            "a hidden picker must never keep a section in the app-wide registry"
        )
        assert getattr(picker, "_nav_section", None) is None
        assert manager.focus_section_for_owner(picker) is False

        picker.showAsSingle(1, _anchor)
        _pump(qapp)
        assert _section(picker) is not None, (
            "re-opening the picker must re-register its section"
        )
    finally:
        _teardown(qapp, host, picker)


def test_down_walks_a_virtualized_panel_past_the_initial_window(qapp):
    """ListPanel virtualizes rows: Down must scroll, not stop at the last live row.

    The panel materializes only its visible window plus overscan, so a naive
    "focus the next live row" walk strands every item below the window. The
    section scrolls one item through the panel's virtual-list controller and
    focuses the row it just bound; the true last item declines.
    """
    items = [f"Item {index}" for index in range(14)]
    host, picker, _anchor, _host_section = _make_picker(qapp, left_items=items)
    try:
        panel = picker.panel_left
        initial_rows = _rows(panel)
        assert _section(picker).owns(initial_rows[0]), (
            "the walk under test is the picker section's, not Qt's native scroll"
        )
        assert len(initial_rows) < len(items), (
            "the probe needs a virtualized panel (fewer live rows than items)"
        )

        _kbd_focus(initial_rows[0], qapp)
        focused = initial_rows[0]
        for _ in range(len(items) - 1):
            QTest.keyClick(focused, Qt.Key.Key_Down)
            focused = _focused(panel)
        assert focused.index == len(items) - 1, (
            "Down must walk the whole virtualized list, not stop at the live window"
        )

        QTest.keyClick(focused, Qt.Key.Key_Down)
        assert QApplication.focusWidget() is focused, (
            "Down at the true last item must decline, never wrap to the top"
        )
    finally:
        _teardown(qapp, host, picker)
