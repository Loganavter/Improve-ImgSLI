"""ScrollValueButton: the owner's real value-change path — focus (a click,
or keyboard) → pill → Up → Left/Right, with NO Enter — and the button must
settle afterwards (sv-hover-fix).

Owner decision 2026-10-19: hovering the button raises NO flyout — the digit
shows inside the button instead (see ``test_hover_alone_shows_digit_not_flyout``
in ``test_scroll_value_button_keyboard_flyout``). The pill is a focus
affordance, so the paths below drive it through focus, not hover.

Two owner-reported symptoms, pinned against the merged build (PR #396):

1. "To enter value-change mode you still need Enter." The owner's real
   interaction is a MOUSE one: click the button -> the value pill appears ->
   Up -> Left/Right step the value. Two gaps stood in the way:
   - the mouse-focus preview was transient before the fix: ``_show_flyout``
     always armed the 700 ms hide timer, so the pill was gone before a hand
     could travel from mouse to keyboard and Up left the row (the pill is
     what Up enters);
   - the focus preview was gated on the toolkit's ``_keyboard_focus``
     (keyboard modality only), so a button focused the mouse way (click)
     showed no pill at all in mouse modality.
   The keyboard-modality path (a key pressed first) works — that is why
   keyboard-only testing missed both.

2. "The button can stick visually in the value-display mode." After the
   pill interaction ends with focus leaving the pill to anywhere OTHER
   than Down/Esc (Tab, window deactivation, a click elsewhere), the pill's
   hide timer was already stopped by its own focusInEvent, so nothing
   hides the pill and nothing settles the anchor: the button keeps the
   hover/value split (the "value/underline" state) while unfocused.

Real ``QTest.keyClick`` presses are used throughout so the app-wide
``NavigationManager`` filter decides, exactly as in the running app.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, declare_navigation_rows
from ui.widgets.scroll_value_button import ScrollValueButton


@pytest.fixture
def host_button(qtbot):
    """A single-row 'toolbar' hosting one ScrollValueButton (value 4) plus
    a second focusable widget (the focus-out / Tab-away target)."""

    host = QWidget()
    host.resize(240, 140)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(24, 24, 24, 24)
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    layout.addWidget(button)
    other = QWidget()
    other.setObjectName("other-focusable")
    other.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(other)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    declare_navigation_rows(host, [host], tag="svb-hover-fix-test")
    try:
        yield host, button
    finally:
        NavigationManager.get_instance().unregister(host)


def _enter_hover(button: ScrollValueButton) -> None:
    pos = button.rect().center()
    local = QPoint(pos).toPointF()
    button.enterEvent(QEnterEvent(local, local, button.mapToGlobal(pos)))


def _leave_hover(button: ScrollValueButton) -> None:
    button.leaveEvent(QEvent(QEvent.Type.Leave))


def _mouse_focus(button: ScrollValueButton) -> None:
    """Focus *button* the way a mouse click does (mouse modality).

    The keyboard-modality grant (a key press first) is the path the merged
    PR #396 already served; the owner's real session is mouse-driven, so the
    focus grant must carry no keyboard modality.
    """
    button.setFocus(Qt.FocusReason.MouseFocusReason)


def _value_rows(button: ScrollValueButton):
    region = button.region("value")
    if region is None:
        return None
    return [
        getattr(row, "text", None) for row in (getattr(region, "rows", None) or [])
    ]


def _settled(button: ScrollValueButton) -> bool:
    """True when the button is back to its resting (non value-display) visual
    state: no hover/value split (single icon region), no suppressed digit."""
    return (
        button._hovered_split is False
        and button._is_scrolling is False
        and {r.id for r in button.regions()} == {"icon"}
    )


# ---------------------------------------------------------------------------
# Symptom 1 — the value-change path must work from a plain click, no Enter
# ---------------------------------------------------------------------------


def test_mouse_focus_then_up_enters_pill_without_enter(host_button, qapp):
    _, button = host_button

    _enter_hover(button)
    _mouse_focus(button)
    qapp.processEvents()

    pill = button._flyout
    assert pill is not None and pill.isVisible(), "mouse focus must preview the value"
    assert pill._label.text() == "4"
    assert button._keyboard_focus is False, "this is the mouse-modality session"

    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()

    assert pill.hasFocus(), "Up must enter the pill after a plain click — no Enter"
    assert QApplication.focusWidget() is pill
    assert not button.hasFocus()


def test_mouse_focus_pill_survives_the_hide_delay_and_up_enters(host_button, qapp):
    """The click-focus preview must not be killed by the 700 ms hide timer
    while the mouse is still on the button (the hand-travel-time gap).

    Hover alone raises no pill (owner decision 2026-10-19); the preview is
    the focus affordance. ``waitExposed`` grants activation focus, so drop it
    first — otherwise ``_mouse_focus`` is a no-op and never re-shows the pill
    with the hover-persistent path.
    """
    _, button = host_button

    button.clearFocus()
    qapp.processEvents()

    _enter_hover(button)
    _mouse_focus(button)
    qapp.processEvents()

    pill = button._flyout
    assert pill is not None and pill.isVisible()

    QTest.qWait(900)  # past _FLYOUT_HIDE_MS — merged code hides the pill here
    qapp.processEvents()

    assert pill.isVisible(), "the mouse-focus preview must persist while hovered"
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    assert pill.hasFocus(), "Up must still enter the pill after the hide delay"


def test_left_right_step_value_after_hover_up(host_button, qapp):
    _, button = host_button

    _enter_hover(button)
    _mouse_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus()

    before = button.get_value()
    QTest.keyClick(pill, Qt.Key.Key_Right)
    assert button.get_value() == before + 1, "Right steps the value inside the pill"
    QTest.keyClick(pill, Qt.Key.Key_Left)
    assert button.get_value() == before, "Left steps back"


def test_focus_alone_shows_preview_in_mouse_modality(host_button, qapp):
    """A button focused the mouse way (click) must preview the value too —
    the merged focus-preview was gated on keyboard modality only."""
    _, button = host_button

    _mouse_focus(button)
    qapp.processEvents()

    pill = button._flyout
    assert pill is not None and pill.isVisible(), (
        "focus must preview the value in mouse modality as well"
    )
    assert not pill.hasFocus(), "the preview must not steal focus"


# ---------------------------------------------------------------------------
# Symptom 2 — the button must settle after every exit path
# ---------------------------------------------------------------------------


def test_settle_after_esc_from_hover_path(host_button, qapp):
    _, button = host_button

    _enter_hover(button)
    _mouse_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus()

    QTest.keyClick(pill, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert not pill.isVisible()
    assert QApplication.focusWidget() is button
    assert button._is_scrolling is False
    assert _value_rows(button) == ["4"], "Esc restores the button's own digit"

    # Mouse leaves — the value-display split must settle back.
    _leave_hover(button)
    qapp.processEvents()
    assert _settled(button), "the button must settle after the pill interaction"


def test_settle_after_click_elsewhere_ends_pill_interaction(host_button, qapp):
    """Focus leaving the pill to another widget must end the interaction:
    the pill hides and the anchor's value split settles.

    Regression: the pill's hide timer was stopped by its own focusInEvent,
    so with no Down/Esc the pill lingered and the anchor kept the
    hover/value split while unfocused — the stuck value-display state.
    (A real mouse click on the second widget: deterministic focus target —
    unlike Tab, which can wrap back onto the anchor and legitimately
    re-show the focus preview.)
    """
    host, button = host_button
    other = host.findChild(QWidget, "other-focusable")

    button.clearFocus()
    QTest.keyClick(button, Qt.Key.Key_F1)  # keyboard modality for the grant
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus(), "Up enters the pill (keyboard-modality path)"

    QTest.mouseClick(other, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert not pill.isVisible(), "the pill must hide when focus leaves it"
    assert QApplication.focusWidget() is not pill
    assert _settled(button), "the anchor must settle once the pill is gone"


def test_keyboard_preview_persists_then_focus_out_hides_it(host_button, qapp):
    """Keyboard focus, no hover: the preview persists — no 700 ms auto-hide
    (owner decision 2026-10-19) — so Up can enter the pill at any time;
    moving the focus ring to another widget takes the pill with it and
    settles the split."""
    host, button = host_button
    other = host.findChild(QWidget, "other-focusable")

    button.clearFocus()
    QTest.keyClick(button, Qt.Key.Key_F1)
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    pill = button._flyout
    assert pill is not None and pill.isVisible()
    assert button._is_scrolling is True
    assert _value_rows(button) == [], "the pill mirrors the value while shown"

    QTest.qWait(900)
    qapp.processEvents()

    assert pill.isVisible(), "the keyboard preview must not auto-hide"
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    assert pill.hasFocus(), "Up enters the still-open preview after the pause"

    other.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    assert not pill.isVisible(), "the pill goes when the focus ring leaves"
    assert button._is_scrolling is False, "the digit is no longer suppressed"
    assert _settled(button), "focus-out settles the split"


def test_settle_after_wheel(host_button, qapp):
    """The wheel preview path: value steps, pill shows, then settles.

    The button is unfocused first (waitExposed hands it activation focus,
    and a focused button legitimately rests on the value split — that is
    the designed focus resting state, not a stuck one).
    """
    _, button = host_button
    button.clearFocus()
    qapp.processEvents()

    from PySide6.QtGui import QWheelEvent

    global_pos = button.mapToGlobal(button.rect().center())
    local_pos = button.rect().center()
    event = QWheelEvent(
        QPoint(local_pos).toPointF(),
        global_pos,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    button.wheelEvent(event)
    qapp.processEvents()

    assert button.get_value() == 5, "the wheel steps the value"
    pill = button._flyout
    assert pill is not None and pill.isVisible(), "the wheel previews the value"

    QTest.qWait(900)
    qapp.processEvents()

    assert not pill.isVisible()
    assert button._is_scrolling is False
    assert _settled(button), "the wheel preview settles on its own"


def test_settle_after_down_returns(host_button, qapp):
    """Down hands the keyboard back; once the mouse leaves, everything
    settles (pill included)."""
    _, button = host_button

    _enter_hover(button)
    _mouse_focus(button)
    QTest.keyClick(button, Qt.Key.Key_Up)
    qapp.processEvents()
    pill = button._flyout
    assert pill.hasFocus()

    QTest.keyClick(pill, Qt.Key.Key_Down)
    qapp.processEvents()

    assert QApplication.focusWidget() is button, "Down hands the keyboard back"
    assert pill.isVisible(), "Down leaves the preview (Up can re-enter)"

    _leave_hover(button)
    qapp.processEvents()

    assert not pill.isVisible(), "leaving the button dismisses the preview"
    assert _settled(button), "the button settles after the mouse leaves"
