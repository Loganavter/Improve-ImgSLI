"""The frame-identity harness catches a stale first paint (and passes settled).

Companion of ``docs/dev/QT_LAYOUT_PITFALLS.md`` (mechanism C): a deferred
reflow runs at the paint boundary via ``PendingSettle``; this harness is how a
surface proves it. Keep the two tests paired — the passing one alone would not
prove the harness can see the bug it exists for.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPaintEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.pending_settle import PendingSettle, settle_on_paint

from tests.helpers.frame_identity import assert_no_stale_paint


class _ValueWidget(QWidget):
    """Records the value it painted, so a stale frame is observable."""

    def __init__(self, value_of) -> None:
        super().__init__()
        self._value_of = value_of
        self.painted: list[str] = []

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        self.painted.append(self._value_of())


def _shown(qapp, widget: _ValueWidget) -> _ValueWidget:
    widget.resize(40, 20)
    widget.show()
    qapp.processEvents()
    widget.painted.clear()
    return widget


def test_harness_passes_when_the_first_paint_is_settled(qapp):
    state = {"value": "old"}
    widget = _shown(qapp, _ValueWidget(lambda: state["value"]))
    pending = PendingSettle()
    settle_on_paint(widget, pending)

    def _mutate() -> None:
        pending.schedule(widget, lambda: state.update(value="new"))
        widget.repaint()

    paints = assert_no_stale_paint(
        widget, mutate=_mutate, observe=lambda: state["value"], qapp=qapp
    )

    assert paints, "the harness recorded no paint"
    assert paints[0] == "new", "the paint boundary did not settle before the first paint"


def test_harness_detects_a_stale_first_paint(qapp):
    state = {"value": "old"}
    widget = _shown(qapp, _ValueWidget(lambda: state["value"]))

    def _mutate() -> None:
        # The pre-fix pattern: coalesce into the next event-loop turn, then
        # repaint — one stale frame goes out, the settled one follows.
        QTimer.singleShot(0, lambda: (state.update(value="new"), widget.update()))
        widget.repaint()

    with pytest.raises(AssertionError, match="intermediate state"):
        assert_no_stale_paint(
            widget, mutate=_mutate, observe=lambda: state["value"], qapp=qapp
        )
