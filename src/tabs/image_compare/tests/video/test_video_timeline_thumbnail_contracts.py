"""Timeline thumbnails: dynamic width preserved, initial/fallback waves use
capped priority indices, and the coordinator prefers visible timeline indices.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md (video timeline thumbnails).
"""

from __future__ import annotations
from types import SimpleNamespace

from PIL import Image

def test_renderer_thumbnail_preserves_dynamic_width():
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        _render_thumbnail_using_renderer,
    )

    def fake_renderer(_snap, _target_w, _target_h, *, auto_crop=False):
        assert auto_crop is False
        return Image.new("RGBA", (640, 180), (255, 0, 0, 255))

    result = _render_thumbnail_using_renderer(
        snap=object(),
        thumbnail_size=(160, 90),
        auto_crop=False,
        render_scale=1.0,
        render_snapshot=fake_renderer,
    )

    assert result is not None
    assert result.size == (320, 90)

def test_thumbnail_service_initial_wave_uses_priority_indices_only(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services.thumbnails import ThumbnailService

    class FakeRecording:
        def evaluate_at(self, _timestamp: float):
            return object()

        def get_duration(self) -> float:
            return 10.0

    service = ThumbnailService()
    queued_indices: list[int] = []
    monkeypatch.setattr(
        service,
        "_queue_thumbnail_worker",
        lambda index, *, priority, track_finish: queued_indices.append(index),
    )

    task_id = service.generate_thumbnails(
        FakeRecording(),
        target_count=50,
        priority_indices=[8, 16, 16, 32],
        fps=60,
    )

    assert task_id > 0
    assert queued_indices == [8, 16, 32]

def test_thumbnail_service_fallback_wave_is_capped(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services.thumbnails import ThumbnailService

    class FakeRecording:
        def evaluate_at(self, _timestamp: float):
            return object()

        def get_duration(self) -> float:
            return 20.0

    service = ThumbnailService()
    queued_indices: list[int] = []
    monkeypatch.setattr(
        service,
        "_queue_thumbnail_worker",
        lambda index, *, priority, track_finish: queued_indices.append(index),
    )

    service.generate_thumbnails(
        FakeRecording(),
        target_count=200,
        priority_indices=[],
        fps=60,
    )

    assert 1 <= len(queued_indices) <= 12

def test_thumbnail_coordinator_prefers_timeline_viewport_indices():
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import ThumbnailCoordinator

    timeline = SimpleNamespace(
        get_visible_thumbnail_frame_indices=lambda overscan_blocks=0: [12, 24, 36],
    )
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: object(),
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(get_current_frame=lambda: 50),
        thumbnail_service=SimpleNamespace(),
        emit_thumbnails_updated=lambda _thumbnails: None,
    )

    assert coordinator.get_visible_frame_indices() == [12, 24, 36]


def test_timeline_resize_debounces_thumbnail_generation(monkeypatch):
    """Window/timeline resize must not queue GPU thumbnails on every pixel."""
    from PySide6.QtCore import QObject

    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    generate_calls: list[list[int]] = []
    thumbnail_service = SimpleNamespace(
        generate_additional_thumbnails=lambda indices, fps=None: generate_calls.append(
            list(indices)
        ),
    )
    timeline = SimpleNamespace(
        get_visible_thumbnail_frame_indices=lambda overscan_blocks=0: [4, 8, 12],
    )
    timer_parent = QObject()
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(),
        thumbnail_service=thumbnail_service,
        emit_thumbnails_updated=lambda _thumbnails: None,
        timer_parent=timer_parent,
    )
    coordinator._test_timer_parent = timer_parent
    pings: list[int] = []
    monkeypatch.setattr(
        coordinator._visible_refresh,
        "ping",
        lambda: pings.append(1),
    )

    coordinator.on_timeline_resized()
    coordinator.on_timeline_viewport_changed()
    coordinator.on_timeline_resized()

    assert pings == [1, 1, 1]
    assert generate_calls == []

    coordinator._refresh_visible_thumbnails()
    assert generate_calls == [[4, 8, 12]]
