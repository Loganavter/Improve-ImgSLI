"""Image carry / Move (DragGhost under cursor) for cross-tab delivery."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QWidget


@pytest.fixture
def carry_service(qapp, monkeypatch, tmp_path):
    import events.image_carry as carry_mod

    monkeypatch.setattr(carry_mod.ImageCarryService, "_instance", None)
    window = QWidget()
    store = SimpleNamespace(
        workspace=SimpleNamespace(active_session_id="s1", sessions=[]),
        get_workspace_session=lambda _sid: None,
        get_active_workspace_session=lambda: None,
        switch_workspace_session=lambda _sid: False,
    )
    service = carry_mod.ImageCarryService(store, window)
    img = tmp_path / "shot.png"
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.red)
    pix.save(str(img), "PNG")
    yield service, img, window
    service.cancel()
    window.deleteLater()


def test_begin_requires_existing_file(carry_service):
    service, img, _window = carry_service
    assert service.begin([img]) is True
    assert service.is_active()
    service.cancel()
    assert not service.is_active()
    assert service.begin([Path("/no/such/file.png")]) is False


def test_begin_hotspot_is_top_right_of_ghost(carry_service):
    service, img, _window = carry_service
    assert service.begin([img]) is True
    # Ghost hangs bottom-left of the cursor (hotspot near top-right of pixmap).
    assert service._hotspot.x() > service._hotspot.y()
    assert service._hotspot.y() == 12
    service.cancel()


def test_finish_ignored_until_armed(carry_service, monkeypatch):
    service, img, window = carry_service
    assert service.begin([img]) is True
    assert not service._armed

    delivered: list[bool] = []
    monkeypatch.setattr(
        service, "_try_deliver", lambda _pos: delivered.append(True) or True
    )

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10, 10),
        QPointF(window.mapToGlobal(QPoint(10, 10))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    service.finish(release)
    assert delivered == []
    assert service.is_active()

    service._armed = True
    service.finish(release)
    assert delivered == [True]
    assert not service.is_active()


def test_schedule_pending_insert_prefers_tab_service(monkeypatch):
    import events.image_carry as carry_mod
    import tabs.registry as registry_mod

    calls: list[tuple] = []

    class FakeRegistry:
        def create_service_for(self, session_type, service_id, paths):
            calls.append((session_type, service_id, list(paths)))
            return True

        def route_drop(self, *_a, **_k):
            raise AssertionError("route_drop should not be used when insert starts")

    monkeypatch.setattr(registry_mod, "TabRegistry", FakeRegistry)

    assert carry_mod._schedule_pending_insert("image_compare", [Path("/tmp/a.png")])
    assert calls == [("image_compare", "begin_pending_image_insert", [Path("/tmp/a.png")])]


def test_router_forwards_carry_before_flyout_dnd(qapp, monkeypatch):
    from events import router
    from events.image_carry import ImageCarryService

    monkeypatch.setattr(ImageCarryService, "_instance", None)
    window = QWidget()
    store = SimpleNamespace()
    carry = ImageCarryService(store, window)
    carry._active = True
    carry._armed = True
    moved: list[int] = []
    finished: list[int] = []
    monkeypatch.setattr(carry, "update_position", lambda _e: moved.append(1))
    monkeypatch.setattr(carry, "finish", lambda _e: finished.append(1))

    dnd = SimpleNamespace(is_dragging=lambda: False)
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(1, 1),
        QPointF(1, 1),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert router.route_drag_and_drop_override(None, move, dnd) is True
    assert moved == [1]

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(1, 1),
        QPointF(1, 1),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert router.route_drag_and_drop_override(None, release, dnd) is True
    assert finished == [1]
    carry.cancel()
    window.deleteLater()
