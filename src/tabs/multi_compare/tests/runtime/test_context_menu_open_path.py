"""Multi Compare context menu opens from contextMenuEvent, not RMB press."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent

from tabs.multi_compare.canvas import interaction as canvas_interaction
from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState


def _canvas():
    leaf = LeafNode(1)
    rect = QRect(0, 0, 100, 100)
    state = MultiCompareState(
        slots=[CompareSlot(id=1, path=None, label="A", image=None)],
        root=leaf,
    )
    return SimpleNamespace(
        state=state,
        ZOOM_STEP=1.1,
        ZOOM_MIN=1.0,
        ZOOM_MAX=50.0,
        _panning=False,
        _leaf_rects=lambda: [(leaf, rect)],
        _do_dispatch=MagicMock(),
        setCursor=MagicMock(),
    )


def test_rmb_press_does_not_open_context_menu(monkeypatch, qapp):
    opened = MagicMock()
    monkeypatch.setattr(canvas_interaction, "open_context_menu", opened)
    widget = _canvas()
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        QPointF(10, 10),
        QPointF(100, 100),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )

    canvas_interaction.handle_mouse_press_event(widget, event)

    opened.assert_not_called()


def test_context_menu_event_opens_slot_menu(monkeypatch, qapp):
    opened = MagicMock(return_value=object())
    monkeypatch.setattr(canvas_interaction, "open_context_menu", opened)
    widget = _canvas()
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(10, 10),
        QPoint(100, 100),
    )

    canvas_interaction.handle_context_menu_event(widget, event)

    opened.assert_called_once()
    request = opened.call_args.args[0]
    assert request.session_type == "multi_compare"
    assert request.target.kind == "multi_compare_slot"
    assert request.target.id == 1
    assert event.isAccepted()
