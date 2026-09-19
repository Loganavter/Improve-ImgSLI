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


def _zoom_coordinator(*, timeline_indices, service, zoom=1.0, total_frames=100):
    """Coordinator variant with a readable zoom scalar on the timeline."""
    coordinator = _coordinator(
        timeline_indices=timeline_indices,
        service=service,
        total_frames=total_frames,
    )
    coordinator.view.timeline._zoom_level = zoom
    return coordinator


def _zoom_service_spy():
    retires: list[int] = []
    pushed: list[list[int]] = []
    additional: list[list[int]] = []
    service = SimpleNamespace(
        retire_in_flight_thumbnails=lambda: retires.append(1),
        set_visible_window=lambda indices: pushed.append(list(indices)),
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
        _generated_indices=set(),
        _pending_indices=set(),
    )
    return service, retires, pushed, additional


def test_zoom_only_refresh_queues_without_retire(qapp):
    """Z4: zoom reshuffles geometry, not content — no token bump."""
    window: list[int] = [4, 8, 12]
    service, retires, pushed, additional = _zoom_service_spy()
    coordinator = _zoom_coordinator(
        timeline_indices=window, service=service, zoom=1.0
    )

    coordinator._refresh_visible_thumbnails()
    assert retires == [], "first refresh establishes the baseline, no retire"
    assert coordinator._last_zoom_level == 1.0
    assert pushed == [[4, 8, 12]]

    # Zoom-only: same window, new zoom → requeue, in-flight wave intact.
    coordinator.view.timeline._zoom_level = 1.25
    coordinator._refresh_visible_thumbnails()
    assert retires == [], "zoom-driven refresh must not retire in-flight thumbs"
    assert additional == [[4, 8, 12], [4, 8, 12]]
    assert coordinator._last_zoom_level == 1.25
    assert pushed[-1] == [4, 8, 12]

    # Zoom + window move together → zoom wins, still no retire, new window queued.
    window[:] = [20, 24]
    coordinator.view.timeline._zoom_level = 1.5
    coordinator._refresh_visible_thumbnails()
    assert retires == [], "zoom change suppresses the retire even as the window moves"
    assert additional[-1] == [20, 24]
    assert coordinator._last_zoom_level == 1.5


def test_scroll_with_stable_zoom_still_retires(qapp):
    """Z4: same zoom + moved window keeps the P3 scroll-cancel."""
    window: list[int] = [4, 8, 12]
    service, retires, _pushed, additional = _zoom_service_spy()
    coordinator = _zoom_coordinator(
        timeline_indices=window, service=service, zoom=1.0
    )

    coordinator._refresh_visible_thumbnails()
    coordinator._refresh_visible_thumbnails()
    assert retires == [], "unchanged window + unchanged zoom must not churn the token"

    window[:] = [20, 24]
    coordinator._refresh_visible_thumbnails()
    assert retires == [1], "scroll/pan (zoom stable) retires as before"
    assert additional[-1] == [20, 24]


def test_zoom_unreadable_keeps_scroll_cancel(qapp):
    """Z4 fail-open: timelines without a zoom scalar behave as before."""
    window: list[int] = [4, 8, 12]
    retires: list[int] = []
    additional: list[list[int]] = []
    service = SimpleNamespace(
        retire_in_flight_thumbnails=lambda: retires.append(1),
        set_visible_window=lambda indices: None,
        generate_additional_thumbnails=(
            lambda indices, fps=None: additional.append(list(indices))
        ),
        _generated_indices=set(),
        _pending_indices=set(),
    )
    coordinator = _coordinator(timeline_indices=window, service=service)

    coordinator._refresh_visible_thumbnails()
    assert coordinator._last_zoom_level is None
    window[:] = [20, 24]
    coordinator._refresh_visible_thumbnails()
    assert retires == [1], "unknown zoom → today's scroll-cancel, no behavior change"


def test_read_zoom_level_prefers_scalar_then_pps(qapp):
    service, _retires, _pushed, _additional = _zoom_service_spy()
    coordinator = _coordinator(timeline_indices=[1], service=service)

    assert coordinator._read_zoom_level() is None

    coordinator.view.timeline.get_pixels_per_second = lambda: 321.0
    assert coordinator._read_zoom_level() == 321.0

    coordinator.view.timeline._zoom_level = 2.0
    assert coordinator._read_zoom_level() == 2.0, (
        "_zoom_level scalar wins over pps when both are readable"
    )


def test_generate_thumbnails_snapshots_zoom_and_pushes_window(qapp):
    """Initial wave records the zoom baseline and pushes the window."""
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    captured: dict = {}
    pushed: list[list[int]] = []
    timeline = SimpleNamespace(
        height=lambda: 200,
        RULER_HEIGHT=24,
        has_snapshots=lambda: True,
        get_total_duration=lambda: 10.0,
        get_pixels_per_second=lambda: 100.0,
        clear_thumbnails=lambda: None,
        get_visible_thumbnail_frame_indices=(
            lambda overscan_blocks=0: [1, 2, 3]
        ),
        _zoom_level=2.0,
    )
    service = SimpleNamespace(
        generate_thumbnails=(
            lambda recording, **kw: captured.update(kw)
        ),
        set_visible_window=lambda indices: pushed.append(list(indices)),
    )
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: object(),
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(),
        thumbnail_service=service,
        emit_thumbnails_updated=lambda _thumbnails: None,
    )

    coordinator.generate_thumbnails()

    assert coordinator._last_zoom_level == 2.0
    assert coordinator._last_visible_indices == [1, 2, 3]
    assert pushed == [[1, 2, 3]]
    assert captured["priority_indices"] == [1, 2, 3]


def _live_service(monkeypatch):
    """Real ThumbnailService with a parked pool and no disk cache."""
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    monkeypatch.setattr(
        service._thread_pool, "start", lambda worker, priority=0: None
    )
    return service


def test_same_generation_out_of_window_completion_dropped(
    qapp, monkeypatch
):
    """Z4 membership: scrolled-away index drops, in-window index applies."""
    service = _live_service(monkeypatch)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))

    generation = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    assert service._pending_indices == {0, 1, 2}

    # Zoom path kept the wave alive while the window narrowed to [0].
    service.set_visible_window([0, 1, 2])
    service.set_visible_window([0])

    service._on_thumbnail_generated(
        2, Image.new("RGBA", _THUMB, (9, 9, 9, 255)), generation
    )
    assert emitted == {}, "out-of-window completion must drop"
    assert 2 not in service._generated_indices

    service._on_thumbnail_generated(
        0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
    )
    assert sorted(emitted) == [0]
    assert 0 in service._generated_indices


def test_unknown_window_applies_completion(qapp, monkeypatch):
    """Z4 fail-open: no window snapshot (or an empty one) applies everything."""
    for window in (None, []):
        service = _live_service(monkeypatch)
        emitted: dict[int, object] = {}
        service.thumbnailReady.connect(
            lambda i, px: emitted.__setitem__(i, px)
        )

        generation = service.generate_thumbnails(
            _FakeRecording(duration=10.0),
            target_count=50,
            priority_indices=[0, 1],
            fps=60,
        )
        if window is None:
            assert service._visible_window is None
        else:
            service.set_visible_window(window)
            assert service._visible_window is None, (
                "empty window must clear to unknown, never filter-all"
            )

        service._on_thumbnail_generated(
            0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
        )
        assert sorted(emitted) == [0], f"window={window!r} must apply"


def test_stale_generation_still_drops_inside_window(qapp, monkeypatch):
    """Z4 guard: the membership filter never rescues a stale generation."""
    service = _live_service(monkeypatch)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))

    generation = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    service.set_visible_window([0, 1, 2])
    retired = service.retire_in_flight_thumbnails()

    service._on_thumbnail_generated(
        1, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
    )
    assert emitted == {}, "stale generation drops even inside the window"
    assert 1 not in service._generated_indices

    service._on_thumbnail_generated(
        1, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), retired
    )
    assert sorted(emitted) == [1]
