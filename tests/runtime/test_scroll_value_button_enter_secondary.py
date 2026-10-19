"""ScrollValueButton: Enter is the SECONDARY ACTION (a right click), not edit mode.

Owner rule (2026-10-20): on the app's scrollable value buttons ``Enter``/
``Return`` must perform exactly what a mouse right click does — emit
``rightClicked`` — so the consumers already wired to that signal open their
colour picker with the keyboard too:

- ``src/tabs/multi_compare/ui/toolbar.py`` —
  ``btn_divider_width.rightClicked`` -> ``_on_divider_width_right_clicked`` ->
  ``divider_color_clicked`` (expert mode: the divider colour picker);
- ``src/plugins/onboarding/pages.py`` — ``b_expert.rightClicked`` ->
  ``_show_color_dialog(...)``.

PRE-CHANGE BEHAVIOUR (red-before, recorded on the pre-change widget with this
file's first two tests): ``keyPressEvent`` treated ``Enter`` as the app-wide
value-edit contract's entry key — ``_enter_edit_mode()`` ran, ``is_editing()``
became ``True`` (so the section gate stopped handing arrows to navigation and
arrows/WASD started stepping the value), the preview pill stayed up as the
readout, and ``rightClicked`` was NOT emitted. A keyboard user therefore could
not reach the divider/guides colour picker at all, and Enter changed the
control's state instead of firing the action the right-click channel carries.

The deliberate exception to the generic Enter-to-edit contract: this control's
keyboard value path is the wheel and the Up-pill's Left/Right (the pill is
entered with Up and steps the value with Left/Right), while Enter is reserved
for the secondary action. ``is_editing()`` stays ``False`` forever, so the
toolkit section gate (``arrow_gate_open``) keeps yielding every arrow to ring
navigation — arrows must never be consumed by this widget while idle.

Real ``QTest.keyClick`` presses are used for the Enter paths so the app-wide
``NavigationManager`` filter decides, exactly as in the running app (guide §11);
the arrow assertions use the trial-dispatch idiom from the toolkit's
``tests/_nav_contract.py`` (a bare, unaccepted ``keyPressEvent`` is how
``ToolbarRowsSection._widget_handles`` probes a widget before claiming a key).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, declare_navigation_rows
from ui.widgets.scroll_value_button import ScrollValueButton


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def host_button(qtbot):
    """A single-row 'toolbar' hosting one ScrollValueButton (value 4)."""

    host = QWidget()
    host.resize(240, 140)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(24, 24, 24, 24)
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    layout.addWidget(button)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    declare_navigation_rows(host, [host], tag="svb-enter-secondary")
    try:
        yield host, button
    finally:
        NavigationManager.get_instance().unregister(host)


def _synthetic_press(widget: QWidget, key: Qt.Key) -> QKeyEvent:
    """Trial-dispatch *key* straight to the widget (no navigation filter)."""
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(event)
    return event


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_emits_right_clicked_exactly_once(host_button, qapp, key):
    """Enter is the right-click channel: one emission, no value change."""
    _, button = host_button
    seen: list[bool] = []
    button.rightClicked.connect(lambda: seen.append(True))
    before = button.get_value()

    button._set_hover_split(True)
    QTest.keyClick(button, key)
    qapp.processEvents()

    assert seen == [True], (
        "Enter must emit rightClicked exactly once (the mouse RMB action)"
    )
    assert button.get_value() == before, "the secondary action must not step the value"
    assert button.is_editing() is False, "Enter must not enter edit mode"


def test_synthetic_enter_does_not_enter_any_edit_state(host_button, qapp):
    """A bare keyPressEvent Enter emits the RMB signal and leaves no edit state."""
    _, button = host_button
    seen: list[bool] = []
    button.rightClicked.connect(lambda: seen.append(True))
    before = button.get_value()

    event = _synthetic_press(button, Qt.Key.Key_Return)

    assert event.isAccepted(), "Enter is handled by this control"
    assert seen == [True]
    assert button.is_editing() is False
    assert getattr(button, "_editing", False) is False
    assert button.get_value() == before


def test_enter_reaches_a_right_click_consumer(host_button, qapp):
    """The exact shape the app consumers use: a zero-argument slot.

    ``multi_compare`` connects ``rightClicked`` to
    ``_on_divider_width_right_clicked`` (which emits ``divider_color_clicked``)
    and onboarding connects ``b_expert.rightClicked`` to a colour-dialog
    helper; both are plain no-argument callables. Pin that the Enter path
    invokes them, so no consumer needs a new connection.
    """
    _, button = host_button
    calls: list[int] = []

    def _on_right_click():  # the consumer's call shape
        calls.append(button.get_value())

    button.rightClicked.connect(_on_right_click)

    QTest.keyClick(button, Qt.Key.Key_Return)
    qapp.processEvents()

    assert calls == [4], "Enter must reach the consumer wired to rightClicked"


@pytest.mark.parametrize(
    "key",
    [
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
    ],
)
def test_arrows_after_enter_stay_unaccepted(host_button, qapp, key):
    """After Enter the arrows are still navigation keys, not value keys.

    ``is_editing()`` is always False, so ``arrow_gate_open`` keeps the section
    gate open and every arrow stays available to ``NavigationManager`` — the
    widget must leave the key unaccepted while idle.
    """
    _, button = host_button
    QTest.keyClick(button, Qt.Key.Key_Return)
    qapp.processEvents()
    before = button.get_value()

    event = _synthetic_press(button, key)

    assert not event.isAccepted(), (
        f"{key!r} must stay available to navigation (widget accepted it while idle)"
    )
    assert button.get_value() == before
    assert button.is_editing() is False
