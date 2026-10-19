"""ScrollValueButton: change the value without Enter (sv-button-ux).

Owner's decisions:
- the value pill is a **preview on focus** (keyboard or mouse) — it never
  steals focus (``grab_focus=False, register_nav_section=True``); hover alone
  shows the digit inside the button and raises no flyout
  (``test_hover_alone_shows_digit_not_flyout``);
- **Up** moves the keyboard *into* the pill, ``Left``/``Right`` step the value
  there (the pill's own ``keyPressEvent`` → ``anchor._step_value``);
- **Down**/*Esc* leave the pill;
- **Enter** mirrors a right-click — it emits ``rightClicked`` and nothing else
  (the control has no edit mode; the pill is entered with Up).

Falsification (recorded in DONE.md): with the pre-change binding — the preview
path force-unregistering the pill's nav section, and ``_ScrollValueFlyout``
inheriting the toolkit's descendant-only ``focus_first_child`` — the pill's
only content is a ``NoFocus`` label, so
``ToolbarRowsSection``'s ``extension_below(...).focus_first_child()`` returns
False and Up falls back to row navigation. ``test_up_enters_pill...`` is red
under that binding.

Real ``QTest.keyClick`` presses are used throughout so the app-wide
``NavigationManager`` filter decides, exactly as in the running app (guide §11).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, declare_navigation_rows
from ui.widgets.scroll_value_button import ScrollValueButton


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
    declare_navigation_rows(host, [host], tag="svb-kbd-test")
    try:
        yield host, button
    finally:
        NavigationManager.get_instance().unregister(host)


def _enter_hover(button: ScrollValueButton) -> None:
    pos = button.rect().center()
    local = QPoint(pos).toPointF()
    button.enterEvent(QEnterEvent(local, local, button.mapToGlobal(pos)))


def _kbd_focus(button: ScrollValueButton) -> None:
    """Focus *button* the way arrow navigation does.

    Ring/focus-preview modality comes from the last input device, not the
    ``FocusReason`` (guide §7), so a real key press must come first. The
    window may already have handed activation focus to the button (first
    focusable child) — ``clearFocus`` first so the key press lands before the
    grant and ``setFocus`` is a real ``FocusIn``, not a no-op.
    """
    button.clearFocus()
    QTest.keyClick(button, Qt.Key.Key_F1)
    button.setFocus(Qt.FocusReason.OtherFocusReason)


def _value_rows(button: ScrollValueButton):
    region = button.region("value")
    if region is None:
        return None
    return [
        getattr(row, "text", None) for row in (getattr(region, "rows", None) or [])
    ]


def test_hover_alone_shows_digit_not_flyout(qtbot):
    """Hover shows the digit inside the button and raises no flyout.

    Owner decision (2026-10-19). A sibling focusable widget owns the
    window's activation focus so the button stays unfocused — otherwise the
    focus preview would raise the pill and suppress the in-button digit.
    """
    host = QWidget()
    host.resize(240, 140)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(24, 24, 24, 24)
    sibling = QWidget()
    sibling.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(sibling)
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    layout.addWidget(button)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    assert not button.hasFocus(), "the sibling must own the activation focus"

    _enter_hover(button)
    qtbot.wait(50)

    assert button._hovered_split is True
    assert button._flyout is None, "hover must not create the value flyout"
    assert _value_rows(button) == ["4"], (
        "hover shows the digit inside the button"
    )


def test_preview_pill_shows_on_keyboard_focus_without_stealing_focus(
    host_button, qapp
):
    _, button = host_button

    _kbd_focus(button)
    qapp.processEvents()

    pill = button._flyout
    assert pill is not None and pill.isVisible(), "keyboard focus must preview too"
    assert not pill.hasFocus()
    assert button.hasFocus()


def test_up_enters_pill_and_left_right_step_value(host_button, qapp):
    _, button = host_button

    _kbd_focus(button)
    qapp.processEvents()
    pill = button._flyout
    assert pill is not None and pill.isVisible()

    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()

    assert pill.hasFocus(), "Up must move the keyboard into the pill"
    assert QApplication.focusWidget() is pill
    assert not button.hasFocus()

    before = button.get_value()
    QTest.keyClick(pill, Qt.Key.Key_Right)
    assert button.get_value() == before + 1, "Right steps the value inside the pill"
    QTest.keyClick(pill, Qt.Key.Key_Left)
    assert button.get_value() == before, "Left steps back"


def test_down_leaves_pill_and_returns_keyboard_to_button(host_button, qapp):
    _, button = host_button

    _kbd_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus()

    QTest.keyClick(pill, Qt.Key.Key_Down)
    qapp.processEvents()

    assert QApplication.focusWidget() is button, "Down hands the keyboard back"
    assert pill.isVisible(), "Down leaves the preview (Up can re-enter), Esc dismisses"


def test_escape_leaves_pill_and_restores_button_digit(host_button, qapp):
    _, button = host_button
    button._set_hover_split(True)

    _kbd_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus()
    assert _value_rows(button) == [], "the pill mirrors the value while shown"

    QTest.keyClick(pill, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert not pill.isVisible()
    assert QApplication.focusWidget() is button
    assert button._is_scrolling is False
    assert _value_rows(button) == ["4"], "Esc restores the button's own digit"


def test_up_inside_pill_leaves_without_stepping(host_button, qapp):
    """A second Up leaves the pill upward — it must never change the value.

    Owner rule (2026-10-19): only Left/Right change the value; Up out of the
    anchor enters the pill, the next Up leaves it (the value must be intact).
    """
    _, button = host_button
    _kbd_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill is not None and pill.hasFocus()
    before = button.get_value()

    QTest.keyClick(pill, Qt.Key.Key_Up)
    qapp.processEvents()

    assert button.get_value() == before, "Up inside the pill must not step the value"


def test_underline_stays_visible_in_the_zero_state(qtbot):
    """The underline is not tied to the value any more.

    Owner rule (2026-10-19): the zero/`zero_icon` state changes what the
    button *shows* (a hidden icon instead of a digit), never whether the
    host-enabled underline is painted.
    """
    button = ScrollValueButton(
        icon=None,
        min_value=0,
        max_value=10,
        start=0,
        zero_icon="divider_hidden",
        show_underline=True,
    )
    qtbot.addWidget(button)
    button.show()
    assert button._is_at_zero() is True
    assert button._underline_visible is True
    assert button._show_underline is True

    button._sync_regions()

    assert button._show_underline is True, "the underline must survive a rebuild"


def test_enter_mirrors_right_click(host_button, qapp):
    """Enter emits ``rightClicked`` (the RMB signal) and does nothing else.

    Owner rule (2026-10-19): the value control has no edit mode — Enter must
    behave like a right-click, not open/step the pill. The pill is entered
    with Up (``test_up_enters_pill_and_left_right_step_value``).
    """
    _, button = host_button
    seen: list[bool] = []
    button.rightClicked.connect(lambda: seen.append(True))

    button._set_hover_split(True)
    before = button.get_value()
    QTest.keyClick(button, Qt.Key.Key_Return)
    qapp.processEvents()

    assert seen == [True], "Enter must emit rightClicked (the RMB signal)"
    assert button.get_value() == before, "Enter must not step the value"
