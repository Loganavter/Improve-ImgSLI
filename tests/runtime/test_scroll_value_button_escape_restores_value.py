"""Enter → Esc on the value flyout must restore the button's own digit.

Regression: the flyout holds keyboard focus in edit mode (Enter), so the
Escape that leaves edit mode arrives at ``_ScrollValueFlyout.keyPressEvent``,
whose Esc branch called ``self.hide()`` directly and never went through
``ScrollValueButton._hide_flyout()``. ``_is_scrolling`` therefore stayed
``True`` (and ``_keyboard_edit_active`` stayed ``True``), so the button's
"value" region kept painting its suppressed/empty rows after the flyout was
gone — the digit vanished instead of reappearing.

The nearest working sibling is the wheel-preview exit: there the flyout does
not take focus, Escape reaches the button's own ``keyPressEvent`` and lands in
``_hide_flyout()``, which resets ``_is_scrolling`` and re-syncs the regions.
Both exit paths must restore the digit.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from ui.widgets.scroll_value_button import ScrollValueButton


def _press(widget, key: Qt.Key) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(event)


def _value_rows_text(button: ScrollValueButton):
    region = button.region("value")
    if region is None:
        return None
    return [getattr(row, "text", None) for row in (getattr(region, "rows", None) or [])]


def _enter_edit_mode(button: ScrollValueButton) -> None:
    # Hover split so the "value" region exists (that is where the digit lives).
    button._set_hover_split(True)
    _press(button, Qt.Key.Key_Return)
    assert button._keyboard_edit_active is True
    assert button._flyout is not None and button._flyout.isVisible()
    assert button._is_scrolling is True
    # While the flyout mirrors the value, the in-button digit is suppressed.
    assert _value_rows_text(button) == []


def test_escape_on_value_flyout_restores_button_digit(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=5)
    qtbot.addWidget(button)
    button.show()

    _enter_edit_mode(button)

    # Enter puts the ring/focus on the flyout, so Esc lands there.
    _press(button._flyout, Qt.Key.Key_Escape)

    assert _value_rows_text(button) == ["5"], (
        "the button's own digit must return after Esc leaves edit mode"
    )
    assert button._is_scrolling is False
    assert button._keyboard_edit_active is False


def test_escape_on_button_still_restores_digit(qtbot):
    """Working sibling: when Escape reaches the button itself (the wheel-preview
    flyout never steals focus), ``_hide_flyout()`` already resets the digit.
    Guard that path so the fix cannot regress it."""
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=3)
    qtbot.addWidget(button)
    button.show()

    _enter_edit_mode(button)

    _press(button, Qt.Key.Key_Escape)

    assert _value_rows_text(button) == ["3"]
    assert button._is_scrolling is False
    assert button._keyboard_edit_active is False
