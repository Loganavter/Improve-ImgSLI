"""Wave B ghosts: drag ghosts parent to the content layer below the strip.

Frozen seam contract (plan-2026-09-25-content-below-strip, section 11):
tab-owned ghosts parent/clamp to the content layer/bounds
(host = ``workspace_content_widget``); a ghost dragged across the strip
band must stay inside content bounds and never paint over the strip.
Startup windows without a content host keep the window-layer fallback
(with warning), never a crash.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.overlay_layer import OverlayLayer
from ui.widgets.drag_ghost_widget import DragGhostWidget

WINDOW_W, WINDOW_H = 800, 600
STRIP_H = 100  # tab-strip band on top; content lives strictly below it.


def _make_shell():
    """Window with a strip band on top + content host below (no .show needed)."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    strip = QWidget(window)
    strip.setObjectName("WorkspaceTabsBar")
    strip.setGeometry(0, 0, WINDOW_W, STRIP_H)
    content = QWidget(window)
    content.setGeometry(0, STRIP_H, WINDOW_W, WINDOW_H - STRIP_H)
    window.workspace_content_widget = content
    tab_page = QWidget(content)
    tab_page.setGeometry(0, 0, WINDOW_W, WINDOW_H - STRIP_H)
    return window, content, tab_page


def _fake_event(global_pos: QPointF):
    return SimpleNamespace(
        globalPosition=lambda: global_pos, position=lambda: global_pos
    )


@pytest.fixture(autouse=True)
def _reset_singletons():
    from events.drag_drop_handler import DragAndDropService
    from events.image_carry import ImageCarryService

    yield
    DragAndDropService._instance = None
    ImageCarryService._instance = None


def _make_dnd_service(window):
    from events.drag_drop_handler import DragAndDropService

    document = SimpleNamespace(
        image_list1=[SimpleNamespace(rating=0)] * 4,
        image_list2=[SimpleNamespace(rating=0)] * 4,
    )
    store = SimpleNamespace(get_session_state_slot=lambda _slot: document)
    return DragAndDropService(store, parent=window)


def _make_row(tab_page):
    from ui.widgets.rating_item import RatingListItem

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
        parent=tab_page,
    )


def test_row_drag_ghost_parents_to_content_host(qapp):
    window, content, tab_page = _make_shell()
    window.show()
    service = _make_dnd_service(window)
    row = _make_row(tab_page)
    row.show()
    try:
        start_global = tab_page.mapToGlobal(QPoint(50, 50))
        service.start_drag(row, _fake_event(QPointF(start_global)))
        assert service.is_dragging()
        ghost = service._ghost_widget
        assert ghost is not None
        assert ghost.parentWidget() is content
    finally:
        service._cleanup()
        row.deleteLater()
        window.deleteLater()


def test_row_drag_ghost_stays_inside_content_across_strip(qapp):
    window, content, tab_page = _make_shell()
    window.show()
    service = _make_dnd_service(window)
    row = _make_row(tab_page)
    row.show()
    try:
        start_global = tab_page.mapToGlobal(QPoint(50, 50))
        service.start_drag(row, _fake_event(QPointF(start_global)))
        ghost = service._ghost_widget
        assert ghost.parentWidget() is content
        # Drag across the strip band (window-local y well above content).
        strip_global = window.mapToGlobal(QPoint(WINDOW_W // 2, STRIP_H // 2))
        service.update_drag_position(_fake_event(QPointF(strip_global)))
        assert content.rect().contains(ghost.geometry())
    finally:
        service._cleanup()
        row.deleteLater()
        window.deleteLater()


def test_carry_ghost_parents_to_content_host_and_clamps(qapp, tmp_path):
    from events.image_carry import ImageCarryService

    window, content, _tab_page = _make_shell()
    window.show()
    store = SimpleNamespace(
        workspace=SimpleNamespace(active_session_id="s1", sessions=[]),
        get_workspace_session=lambda _sid: None,
        get_active_workspace_session=lambda: None,
        switch_workspace_session=lambda _sid: False,
    )
    service = ImageCarryService(store, window)
    img = tmp_path / "shot.png"
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.red)
    pix.save(str(img), "PNG")
    try:
        assert service.begin([Path(img)]) is True
        ghost = service._ghost_widget
        assert ghost is not None
        assert ghost.parentWidget() is content
        # Push the ghost into the strip band; it must clamp back to content.
        strip_global = window.mapToGlobal(QPoint(WINDOW_W // 2, STRIP_H // 2))
        service._move_ghost(strip_global)
        assert content.rect().contains(ghost.geometry())
    finally:
        service.cancel()
        window.deleteLater()


def test_ghost_falls_back_to_window_layer_when_content_host_absent(
    qapp, tmp_path, caplog
):
    """Startup window without a content host: window layer + warning."""
    from events.image_carry import ImageCarryService

    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    store = SimpleNamespace(
        workspace=SimpleNamespace(active_session_id="s1", sessions=[]),
        get_workspace_session=lambda _sid: None,
        get_active_workspace_session=lambda: None,
        switch_workspace_session=lambda _sid: False,
    )
    service = ImageCarryService(store, window)
    img = tmp_path / "shot.png"
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.red)
    pix.save(str(img), "PNG")
    try:
        with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
            assert service.begin([Path(img)]) is True
        assert service._ghost_widget.parentWidget() is window
        assert any(
            "workspace_content_widget" in rec.getMessage()
            for rec in caplog.records
        )
    finally:
        service.cancel()
        window.deleteLater()


def test_drag_ghost_widget_none_parent_mentions_content(qapp):
    with pytest.raises(ValueError, match="in-content parent"):
        DragGhostWidget(None)
