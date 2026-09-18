"""P3 wave discipline — structure contracts, no timing asserts.

Proves: the initial wave queue equals the visible window exactly (no
fallback spread appended on top); the ``<= 12`` fallback stays capped for
the genuinely-unknown case (empty visible window); a viewport change
retires in-flight workers (generation bump, stale completion dropped,
pending cleared for immediate re-queue) while finished progress and the
P2 cache-hit path (instant emit, zero workers) survive; the initial
wave's ``generationFinished`` queues the unseen remainder at background
priority without re-emitting (no second scheduler, no loop).

Dogma source: THUMB_PLAN.md (P3) — visible-only initial wave, idle
background fill, scroll-cancel; timing assertions live only in
logs/manual runs, never here.
"""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image


_THUMB = (160, 90)


class _FakeRecording:
    """Duck-typed recording with a real duration (frame-count math only)."""

    def __init__(self, duration=20.0):
        self._duration = duration

    def evaluate_at(self, _timestamp: float):
        return object()

    def get_duration(self) -> float:
        return self._duration


def _capture_service(monkeypatch):
    """Real ThumbnailService with worker queueing captured, nothing run."""
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    service = ThumbnailService()
    queued: list[tuple[int, int, bool]] = []
    monkeypatch.setattr(
        service,
        "_queue_thumbnail_worker",
        lambda index, *, priority, track_finish: queued.append(
            (index, priority, track_finish)
        ),
    )
    return service, queued


def test_initial_wave_queue_equals_visible_window_exactly(monkeypatch):
    service, queued = _capture_service(monkeypatch)

    generation = service.generate_thumbnails(
        _FakeRecording(duration=20.0),  # 1201 frames: fallback would differ
        target_count=200,
        priority_indices=[5, 6, 7, 8],
        fps=60,
    )

    assert generation > 0
    assert [idx for idx, _, _ in queued] == [5, 6, 7, 8], (
        "initial wave must be exactly the visible window — "
        "no fallback spread on top"
    )
    assert {priority for _, priority, _ in queued} == {0}
    assert all(track for _, _, track in queued)


def test_unknown_view_fallback_stays_capped(monkeypatch):
    for priority in ([], None):
        service, queued = _capture_service(monkeypatch)
        service.generate_thumbnails(
            _FakeRecording(duration=20.0),
            target_count=200,
            priority_indices=priority,
            fps=60,
        )
        assert 1 <= len(queued) <= 12, (
            "genuinely-unknown viewport (empty visible window) keeps "
            "the bounded probe"
        )


def test_scroll_retires_in_flight_and_stale_completion_dropped(
    qapp, monkeypatch
):
    """Viewport change bumps the token; pre-scroll arrivals drop on arrival."""
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    service = ThumbnailService()
    # No disk cache here: the wave/token assertions must not consult the
    # real user cache dir (nor populate it — object() snaps key
    # deterministically and would poison later runs).
    service.set_thumbnail_disk_cache(None)
    # Parked pool: workers never run, so indices stay in-flight.
    monkeypatch.setattr(
        service._thread_pool, "start", lambda worker, priority=0: None
    )
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))
    finished: list[int] = []
    service.generationFinished.connect(lambda: finished.append(1))

    generation = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    assert service._pending_indices == {0, 1, 2}
    assert service._active_workers == 3

    retired = service.retire_in_flight_thumbnails()

    assert retired == generation + 1
    assert service._pending_indices == set(), (
        "retire must clear pending so the refresh re-queues "
        "overlapping indices immediately"
    )
    assert service._active_workers == 0

    # Late arrival from the retired wave: pixmap AND counter both drop.
    service._on_thumbnail_generated(
        0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
    )
    assert emitted == {}
    assert 0 not in service._generated_indices
    service._on_worker_finished(generation)
    assert finished == [], "retired wave must never finish late"

    # The live token still works after the retire.
    service._on_thumbnail_generated(
        0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), retired
    )
    assert sorted(emitted) == [0]
    assert 0 in service._generated_indices


def _write_source(path, color=(200, 100, 50)):
    Image.new("RGB", (64, 36), color).save(str(path), "PNG")
    return str(path)


def _snap(*, path1, path2, timestamp=0.0, split=0.5, frame=0):
    return SimpleNamespace(
        timestamp=timestamp,
        image1_path=path1,
        image2_path=path2,
        name1="a",
        name2="b",
        viewport_state={"frame": frame, "split": split},
        settings_state={"mode": "compare"},
    )


class _SnapRecording:
    """Duck-typed recording mapping timestamps back to per-index snaps."""

    def __init__(self, snaps, duration=10.0, fps=60):
        self._snaps = list(snaps)
        self._duration = duration
        self._fps = fps

    def evaluate_at(self, timestamp: float):
        idx = min(
            max(0, int(round(float(timestamp) * self._fps))),
            len(self._snaps) - 1,
        )
        return self._snaps[idx]

    def get_duration(self) -> float:
        return self._duration


def test_retire_keeps_cache_hit_path_worker_free(qapp, monkeypatch, tmp_path):
    """P2 hit path after a retire: instant emit, zero renderer calls."""
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        ThumbnailDiskCache,
    )
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    src1 = _write_source(tmp_path / "img1.png")
    src2 = _write_source(tmp_path / "img2.png")
    snaps = [
        _snap(path1=src1, path2=src2, timestamp=i / 60.0, frame=i)
        for i in range(3)
    ]
    cache = ThumbnailDiskCache(cache_dir=str(tmp_path / "thumbcache"))
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(cache)
    monkeypatch.setattr(
        service._thread_pool, "start", lambda worker, priority=0: worker.run()
    )
    calls: list[tuple] = []

    def fake_render(snap, w, h, *, auto_crop=False):
        calls.append((w, h, auto_crop))
        return Image.new("RGBA", _THUMB, (50, 100, 150, 255))

    service.set_snapshot_renderer(fake_render)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))
    finished: list[int] = []
    service.generationFinished.connect(lambda: finished.append(1))
    recording = _SnapRecording(snaps)

    service.generate_thumbnails(
        recording,
        target_count=50,
        thumbnail_size=_THUMB,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    assert len(calls) == 3
    assert sorted(emitted) == [0, 1, 2]

    service.retire_in_flight_thumbnails()

    # Warm wave after the retire: every index is a P2 hit.
    service.generate_thumbnails(
        recording,
        target_count=50,
        thumbnail_size=_THUMB,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    assert len(calls) == 3, "warm wave must not call the renderer"
    assert sorted(emitted) == [0, 1, 2]
    assert finished == [1, 1], "cache-hit wave must still finish the generation"


def _coordinator(*, timeline_indices, service, total_frames=100):
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    timeline = SimpleNamespace(
        get_visible_thumbnail_frame_indices=(
            lambda overscan_blocks=0: list(timeline_indices)
        ),
    )
    return ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: object(),
            get_fps=lambda: 60,
            get_frame_count=lambda: total_frames,
        ),
        playback_engine=SimpleNamespace(),
        thumbnail_service=service,
        emit_thumbnails_updated=lambda _thumbnails: None,
    )


def test_generation_finished_queues_idle_remainder(qapp):
    additional: list[list[int]] = []
    service = SimpleNamespace(
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
        _generated_indices={0, 1},
        _pending_indices={2},
    )
    coordinator = _coordinator(
        timeline_indices=[0, 1], service=service, total_frames=5
    )

    assert coordinator.on_thumbnails_generation_finished() is None
    assert additional == [[3, 4]], (
        "idle fill must queue every still-unseen index exactly once"
    )


def test_generation_finished_noop_when_nothing_unseen(qapp):
    additional: list[list[int]] = []
    service = SimpleNamespace(
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
        _generated_indices={0, 1, 2},
        _pending_indices=set(),
    )
    coordinator = _coordinator(
        timeline_indices=[0, 1], service=service, total_frames=3
    )

    assert coordinator.on_thumbnails_generation_finished() is None
    assert additional == []

    # No editor service: must not crash, must not queue.
    coordinator.editor_service = None
    assert coordinator.on_thumbnails_generation_finished() is None
    assert additional == []


def test_refresh_retires_only_when_wanted_set_changed(qapp):
    window: list[int] = [4, 8, 12]
    retires: list[int] = []
    additional: list[list[int]] = []
    service = SimpleNamespace(
        retire_in_flight_thumbnails=lambda: retires.append(1),
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
        _generated_indices=set(),
        _pending_indices=set(),
    )
    coordinator = _coordinator(timeline_indices=window, service=service)

    coordinator._refresh_visible_thumbnails()
    assert retires == [], "first refresh establishes the baseline, no retire"
    assert additional == [[4, 8, 12]]

    coordinator._refresh_visible_thumbnails()
    assert retires == [], "unchanged window must not churn the token"
    assert additional == [[4, 8, 12], [4, 8, 12]]

    window[:] = [20, 24]
    coordinator._refresh_visible_thumbnails()
    assert retires == [1], "changed wanted set retires in-flight workers"
    assert additional[-1] == [20, 24]


def test_refresh_without_retire_seam_stays_visible_only(qapp):
    """Services without the retire seam keep the plain visible-only refresh."""
    additional: list[list[int]] = []
    service = SimpleNamespace(
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
    )
    coordinator = _coordinator(timeline_indices=[4, 8, 12], service=service)

    coordinator._refresh_visible_thumbnails()

    assert additional == [[4, 8, 12]]
