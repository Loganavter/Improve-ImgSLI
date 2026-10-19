"""Escape on the value pill must restore the button's own digit.

Regression: while the pill holds keyboard focus (Up moved the keyboard into
it), the Escape that dismisses it arrived at
``_ScrollValueFlyout.keyPressEvent``, whose Esc branch called ``self.hide()``
directly and never went through ``ScrollValueButton._hide_flyout()``.
``_is_scrolling`` therefore stayed ``True``, so the button's "value" region
kept painting its suppressed/empty rows after the flyout was gone — the digit
vanished instead of reappearing.

The nearest working sibling is the wheel-preview exit: there the flyout does
not take focus, Escape reaches the button's own ``keyPressEvent`` and lands in
``_dismiss_preview()``, which goes through ``_hide_flyout()`` and resets
``_is_scrolling``. Both exit paths must restore the digit.
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


def _open_value_pill(button: ScrollValueButton) -> None:
    # Hover split so the "value" region exists (that is where the digit lives).
    button._set_hover_split(True)
    button._show_flyout()
    assert button._flyout is not None and button._flyout.isVisible()
    assert button._is_scrolling is True
    # While the flyout mirrors the value, the in-button digit is suppressed.
    assert _value_rows_text(button) == []


def test_escape_on_value_flyout_restores_button_digit(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=5)
    qtbot.addWidget(button)
    button.show()

    _open_value_pill(button)

    # Up puts the keyboard on the pill, so Esc lands there.
    _press(button._flyout, Qt.Key.Key_Escape)

    assert not button._flyout.isVisible()
    assert _value_rows_text(button) == ["5"], (
        "the button's own digit must return after Esc dismisses the pill"
    )
    assert button._is_scrolling is False


def test_escape_on_button_still_restores_digit(qtbot):
    """Working sibling: when Escape reaches the button itself (the wheel-preview
    flyout never steals focus), ``_dismiss_preview()`` already resets the digit.
    Guard that path so the fix cannot regress it."""
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=3)
    qtbot.addWidget(button)
    button.show()

    _open_value_pill(button)

    _press(button, Qt.Key.Key_Escape)

    assert _value_rows_text(button) == ["3"]
    assert button._is_scrolling is False
