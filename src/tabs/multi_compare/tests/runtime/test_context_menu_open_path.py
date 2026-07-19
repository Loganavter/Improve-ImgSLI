"""Multi Compare context menu matches Image Compare (manager defaults)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent

from tabs.multi_compare.canvas import interaction as canvas_interaction
from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState


def _canvas_stub():
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
        window=lambda: MagicMock(name="window"),
    )


def test_rmb_press_does_not_open_context_menu(monkeypatch, qapp):
    opened = MagicMock()
    monkeypatch.setattr(canvas_interaction, "open_context_menu", opened)
    widget = _canvas_stub()
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


def test_context_menu_event_matches_image_compare_defaults(monkeypatch, qapp):
    menu = MagicMock()
    menu.aboutToHide = MagicMock()
    menu.aboutToHide.connect = MagicMock()
    menu.is_popup_surface = MagicMock(return_value=True)
    opened = MagicMock(return_value=menu)
    monkeypatch.setattr(canvas_interaction, "open_context_menu", opened)
    monkeypatch.delenv("IMGSLI_MC_RMB_SURFACE", raising=False)
    widget = _canvas_stub()
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(10, 10),
        QPoint(100, 100),
    )

    canvas_interaction.handle_context_menu_event(widget, event)

    opened.assert_called_once()
    request = opened.call_args.args[0]
    assert request.source_widget is widget
    assert request.surface is None
    assert request.menu_parent is None
    assert request.session_type == "multi_compare"
    assert request.target.id == 1
    assert event.isAccepted()
    menu.aboutToHide.connect.assert_not_called()


def test_context_menu_surface_env_override(monkeypatch, qapp):
    from tabs.multi_compare.canvas.interaction import _rmb_surface_override

    monkeypatch.setenv("IMGSLI_MC_RMB_SURFACE", "in_window")
    assert _rmb_surface_override() == "in_window"
    monkeypatch.setenv("IMGSLI_MC_RMB_SURFACE", "popup")
    assert _rmb_surface_override() == "popup"
    monkeypatch.delenv("IMGSLI_MC_RMB_SURFACE", raising=False)
    assert _rmb_surface_override() is None
