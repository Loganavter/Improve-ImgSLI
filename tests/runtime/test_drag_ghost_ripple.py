"""Drag ghost must not capture the row's in-flight ripple.

Regression: starting a drag happened right after the press, while the
row's ripple wave was still animating — ``DragAndDropService.start_drag``
grabbed the row's pixmap with the half-finished ripple baked in. The
ripple is cancelled before the grab.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QWidget

from events.drag_drop_handler import DragAndDropService, _cancel_ripple
from ui.widgets.rating_item import RatingListItem


@pytest.fixture(autouse=True)
def _reset_drag_service():
    yield
    DragAndDropService._instance = None


def _fake_event(pos: QPointF):
    return SimpleNamespace(globalPosition=lambda: pos, position=lambda: pos)


def _make_service(host: QWidget) -> DragAndDropService:
    document = SimpleNamespace(
        image_list1=[SimpleNamespace(rating=0)] * 4,
        image_list2=[SimpleNamespace(rating=0)] * 4,
    )
    store = SimpleNamespace(
        get_session_state_slot=lambda _slot: document,
    )
    return DragAndDropService(store, parent=host)


def _make_row() -> RatingListItem:
    return RatingListItem(
        index=0,
        text="shot.png",
        rating=1,
        full_path="/tmp/shot.png",
        list_num=1,
        get_rating=lambda *args, **kwargs: 1,
        increment_rating=lambda *args, **kwargs: None,
        decrement_rating=lambda *args, **kwargs: None,
        create_rating_gesture=lambda *args, **kwargs: None,
        on_update_drop_indicator=lambda *args, **kwargs: None,
        on_clear_drop_indicator=lambda: None,
        is_current=True,
    )


def test_cancel_ripple_clears_in_flight_wave(qapp):
    row = _make_row()
    row._ripple.trigger(QRectF(row.rect()).center())
    assert row._ripple.is_active()

    _cancel_ripple(row)

    assert not row._ripple.is_active()
    row.deleteLater()


def test_start_drag_cancels_ripple_before_grab(qapp):
    host = QWidget()
    host.show()
    service = _make_service(host)
    row = _make_row()
    row.show()
    qapp.processEvents()
    row._ripple.trigger(QRectF(row.rect()).center())
    assert row._ripple.is_active()

    service.start_drag(row, _fake_event(QPointF(50, 50)))

    assert not row._ripple.is_active()
    assert service.is_dragging()
    assert service._ghost_widget is not None
    service._cleanup()
    row.deleteLater()
