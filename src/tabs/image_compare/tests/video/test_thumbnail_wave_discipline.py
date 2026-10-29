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
    """Coordinator variant with a readable zoom scalar on the timeline.

    Zoom is driven through the public ``get_pixels_per_second`` API —
    the coordinator must never read the toolkit-private ``_zoom_level``.
    """
    coordinator = _coordinator(
        timeline_indices=timeline_indices,
        service=service,
        total_frames=total_frames,
    )
    coordinator.view.timeline.get_pixels_per_second = lambda: zoom
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
    coordinator.view.timeline.get_pixels_per_second = lambda: 1.25
    coordinator._refresh_visible_thumbnails()
    assert retires == [], "zoom-driven refresh must not retire in-flight thumbs"
    assert additional == [[4, 8, 12], [4, 8, 12]]
    assert coordinator._last_zoom_level == 1.25
    assert pushed[-1] == [4, 8, 12]

    # Zoom + window move together → zoom wins, still no retire, new window queued.
    window[:] = [20, 24]
    coordinator.view.timeline.get_pixels_per_second = lambda: 1.5
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


def test_read_zoom_level_uses_public_pps_only(qapp):
    """C-A: zoom reads go through get_pixels_per_second, never _zoom_level."""
    service, _retires, _pushed, _additional = _zoom_service_spy()
    coordinator = _coordinator(timeline_indices=[1], service=service)

    assert coordinator._read_zoom_level() is None

    coordinator.view.timeline.get_pixels_per_second = lambda: 321.0
    assert coordinator._read_zoom_level() == 321.0

    coordinator.view.timeline._zoom_level = 2.0
    assert coordinator._read_zoom_level() == 321.0, (
        "toolkit-private _zoom_level must be ignored even when present"
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

    assert coordinator._last_zoom_level == 100.0
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
    """I4 membership: completion outside the CAPTURED window drops.

    The filter reads the window snapshot taken at queue time, never the
    live window: after the initial wave queues {0, 1, 2}, an additional
    queue for [3] extends the capture to {0, 1, 2, 3}, and index 7 still
    drops while index 3 applies.
    """
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
    assert service._generation_windows[generation] == frozenset({0, 1, 2})

    # Idle-fill style extension of the same generation's capture.
    service.generate_additional_thumbnails([3])
    assert service._generation_windows[generation] == frozenset({0, 1, 2, 3})

    service._on_thumbnail_generated(
        7, Image.new("RGBA", _THUMB, (9, 9, 9, 255)), generation
    )
    assert emitted == {}, "out-of-captured-window completion must drop"
    assert 7 not in service._generated_indices

    service._on_thumbnail_generated(
        3, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
    )
    assert sorted(emitted) == [3]
    assert 3 in service._generated_indices


def test_membership_uses_captured_window_not_live(qapp, monkeypatch):
    """I4: the live window never overrides the captured one.

    The zoom path keeps the wave alive (no retire) while pushing a new
    live window. A same-generation completion inside the CAPTURED window
    still applies even when the live window moved away, and a completion
    outside the capture drops even when the live window contains it.
    """
    service = _live_service(monkeypatch)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))

    generation = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0, 1, 2],
        fps=60,
    )

    # Zoom remap: live window narrows, wave (and its capture) intact.
    service.set_visible_window([0])

    service._on_thumbnail_generated(
        2, Image.new("RGBA", _THUMB, (9, 9, 9, 255)), generation
    )
    assert sorted(emitted) == [2], (
        "captured in-window completion applies despite the live window"
    )

    # Live window widens, capture does not follow without a queue.
    service.set_visible_window([0, 1, 2, 9])
    service._on_thumbnail_generated(
        9, Image.new("RGBA", _THUMB, (4, 5, 6, 255)), generation
    )
    assert sorted(emitted) == [2], (
        "outside-capture completion drops despite the live window"
    )
    assert 9 not in service._generated_indices


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


def test_late_a_over_fresh_b_dropped(qapp, monkeypatch):
    """I4 identity: generation A's pixels never overwrite generation B's.

    Wave A queues index 0, scroll retires it, wave B re-queues index 0.
    A's completion arrives late with a distinct payload; B's arrives with
    its own. The surviving pixmap bytes must be B's, never A's.
    """
    from PySide6.QtGui import QImage

    service = _live_service(monkeypatch)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))

    generation_a = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0],
        fps=60,
    )
    generation_b = service.retire_in_flight_thumbnails()
    assert generation_b == generation_a + 1
    service.generate_additional_thumbnails([0])
    assert service._pending_indices == {0}

    payload_a = Image.new("RGBA", _THUMB, (255, 0, 0, 255))
    payload_b = Image.new("RGBA", _THUMB, (0, 255, 0, 255))
    service._on_thumbnail_generated(0, payload_a, generation_a)
    assert emitted == {}, "late A completion must drop"
    service._on_thumbnail_generated(0, payload_b, generation_b)
    assert sorted(emitted) == [0]

    surviving = emitted[0].toImage().convertToFormat(
        QImage.Format.Format_RGBA8888
    )
    assert surviving.pixelColor(0, 0).getRgb() == (0, 255, 0, 255)


def test_bulk_thumbnails_generated_emits_full_dict(qapp, monkeypatch):
    """I4 bulk revive: wave completion emits the full dict once.

    The synchronous pool runs every worker inline, so the tracked wave
    completes inside ``generate_thumbnails``: one ``thumbnailsGenerated``
    with every index, then the idle-fill ``generationFinished`` with no
    second bulk (no loop, no scheduler).
    """
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    monkeypatch.setattr(
        service._thread_pool, "start", lambda worker, priority=0: worker.run()
    )

    def fake_render(snap, w, h, *, auto_crop=False):
        return Image.new("RGBA", _THUMB, (50, 100, 150, 255))

    service.set_snapshot_renderer(fake_render)
    bulk: list[dict] = []
    service.thumbnailsGenerated.connect(lambda thumbs: bulk.append(dict(thumbs)))
    finished: list[int] = []
    service.generationFinished.connect(lambda: finished.append(1))

    service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        thumbnail_size=_THUMB,
        priority_indices=[0, 1],
        fps=60,
    )

    assert finished == [1]
    assert len(bulk) == 1, "completed wave emits exactly one bulk replace"
    assert sorted(bulk[0]) == [0, 1]
    assert all(not px.isNull() for px in bulk[0].values())


def test_empty_wave_emits_no_bulk(qapp, monkeypatch):
    """I4 bulk guard: a fully-dropped wave must not wipe the strip.

    Every completion drops (stale token), so the accumulator stays empty
    and the finish emits ``generationFinished`` with no ``{}`` bulk.
    """
    service = _live_service(monkeypatch)
    bulk: list[dict] = []
    service.thumbnailsGenerated.connect(lambda thumbs: bulk.append(dict(thumbs)))
    finished: list[int] = []
    service.generationFinished.connect(lambda: finished.append(1))

    generation = service.generate_thumbnails(
        _FakeRecording(duration=10.0),
        target_count=50,
        priority_indices=[0, 1],
        fps=60,
    )
    stale = generation
    service.retire_in_flight_thumbnails()
    for _ in range(2):
        service._on_worker_finished(stale)
    assert finished == [], "retired wave must never finish late"

    live = service._generation
    service.generate_additional_thumbnails([0, 1])
    for _ in range(2):
        service._on_thumbnail_generated(
            0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), stale
        )
    service._on_worker_finished(live)
    assert finished == [1]
    assert bulk == [], "empty accumulator must not emit an empty replace"


def _tagged_coordinator(service, window, zoom=100.0):
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    added: list[int] = []
    timeline = SimpleNamespace(
        height=lambda: 200,
        RULER_HEIGHT=24,
        has_snapshots=lambda: True,
        get_total_duration=lambda: 10.0,
        get_pixels_per_second=lambda: zoom,
        clear_thumbnails=lambda: None,
        add_thumbnail=lambda idx, _px: added.append(idx),
        get_visible_thumbnail_frame_indices=(
            lambda overscan_blocks=0: list(window)
        ),
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
    return coordinator, added


def test_coordinator_mirrors_feed_generation(qapp):
    """I4: the coordinator mirrors the queued token for tagged drops."""
    service = SimpleNamespace(
        generate_thumbnails=lambda recording, **kw: 7,
        retire_in_flight_thumbnails=lambda: 8,
        set_visible_window=lambda indices: None,
        generate_additional_thumbnails=lambda indices, fps=None: None,
    )
    coordinator, added = _tagged_coordinator(service, [1, 2, 3])
    assert coordinator._feed_generation is None

    coordinator.generate_thumbnails()
    assert coordinator._feed_generation == 7

    coordinator.on_single_thumbnail_ready(1, object(), generation=6)
    assert added == [], "stale-tagged completion drops before add_thumbnail"
    coordinator.on_single_thumbnail_ready(1, object(), generation=7)
    assert added == [1]
    coordinator.on_single_thumbnail_ready(2, object(), generation=None)
    assert added == [1, 2], "untagged completion fails open (today's wiring)"


def test_coordinator_refresh_tracks_retired_token(qapp):
    """I4: the scroll-retire path moves the mirror to the retired token."""
    window: list[int] = [4, 8, 12]
    service = SimpleNamespace(
        generate_thumbnails=lambda recording, **kw: 7,
        retire_in_flight_thumbnails=lambda: 8,
        set_visible_window=lambda indices: None,
        generate_additional_thumbnails=lambda indices, fps=None: None,
        _generated_indices=set(),
        _pending_indices=set(),
    )
    coordinator, added = _tagged_coordinator(service, window)
    coordinator.generate_thumbnails()
    assert coordinator._feed_generation == 7

    window[:] = [20, 24]
    coordinator._refresh_visible_thumbnails()
    assert coordinator._feed_generation == 8, (
        "retire must move the mirror so wave-7 arrivals drop"
    )
    coordinator.on_single_thumbnail_ready(20, object(), generation=7)
    assert added == []
    coordinator.on_single_thumbnail_ready(20, object(), generation=8)
    assert added == [20]


def test_coordinator_bulk_applies_atomic_replace(qapp):
    """I4: the bulk dict applies via set_thumbnails, never a wipe.

    With a widget seam the coordinator applies the atomic replace
    directly and skips the presenter re-emit (whose Signal(dict) hop
    QVariantMap-converts pixmap values away — re-emitting would wipe the
    strip with ``{}``). Without a widget it fails open through the emit.
    """
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    replaced: list[dict] = []
    fanned: list[dict] = []
    timeline = SimpleNamespace(set_thumbnails=lambda thumbs: replaced.append(thumbs))
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(),
        playback_engine=SimpleNamespace(),
        thumbnail_service=SimpleNamespace(),
        emit_thumbnails_updated=lambda thumbs: fanned.append(thumbs),
    )
    payload = {0: object(), 1: object()}

    coordinator.on_thumbnails_generated(payload)

    assert len(replaced) == 1
    assert replaced[0] == payload
    assert replaced[0] is not payload, "widget gets a copy, not the live dict"
    assert fanned == [], "applied replace must not re-emit (wipe risk)"

    coordinator.view = None
    coordinator.on_thumbnails_generated(payload)
    assert fanned == [payload], "no widget → fail open through the emit"


# ---------------------------------------------------------------------------
# C-A app wiring: presenter connect/disconnect symmetry, frame-count owner,
# teardown clearing, detach cancel, viewport-helper optimal count.
# ---------------------------------------------------------------------------

import ast as _ast
import re as _re
from pathlib import Path as _Path

_FROZEN_TIMELINE_SIGNALS = {
    "viewportChanged",
    "zoomChanged",
    "viewportChangedState",
}

_THIS_DIR = _Path(__file__).resolve().parent
_SRC_ROOT = _THIS_DIR.parents[3]
_PRESENTER_PATH = (
    _SRC_ROOT
    / "tabs"
    / "image_compare"
    / "plugins"
    / "video_editor"
    / "presenter.py"
)
_THUMB_COORD_PATH = (
    _SRC_ROOT
    / "tabs"
    / "image_compare"
    / "plugins"
    / "video_editor"
    / "presenter_parts"
    / "thumbnails.py"
)
_THUMB_SVC_PATH = (
    _SRC_ROOT
    / "tabs"
    / "image_compare"
    / "plugins"
    / "video_editor"
    / "services"
    / "thumbnails.py"
)


def _read_source(path):
    return _Path(path).read_text(encoding="utf-8")


def test_view_signal_connect_disconnect_symmetry():
    """C-A(a): every view/timeline connect has a disconnect; frozen surface.

    Proves the rg-balanced audit structurally: the set of signals connected
    in ``_connect_view_signals`` is covered by ``_disconnect_view_signals``,
    the timeline subset is exactly the frozen
    ``zoomChanged/viewportChanged/viewportChangedState`` surface (no
    ``resized``/``layoutSettled``), and ``_on_view_destroyed`` disconnects.
    """
    src = _read_source(_PRESENTER_PATH)
    tree = _ast.parse(src)
    funcs = {
        node.name: node
        for node in _ast.walk(tree)
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
    }
    connect_src = _ast.get_source_segment(src, funcs["_connect_view_signals"])
    disconnect_src = _ast.get_source_segment(
        src, funcs["_disconnect_view_signals"]
    )
    destroyed_src = _ast.get_source_segment(src, funcs["_on_view_destroyed"])
    assert connect_src and disconnect_src and destroyed_src

    connected = set(_re.findall(r"\.(\w+)\.connect\(", connect_src))
    assert connected, "expected view signal connects"
    missing = {
        name for name in connected if f'"{name}"' not in disconnect_src
    }
    assert not missing, (
        f"signals connected without a disconnect mirror: {sorted(missing)}"
    )

    timeline_connected = set(
        _re.findall(r"timeline\.(\w+)\.connect\(", connect_src)
    )
    assert timeline_connected, "expected timeline signal connects"
    assert timeline_connected <= _FROZEN_TIMELINE_SIGNALS, (
        f"timeline surface must stay frozen: {sorted(timeline_connected)}"
    )
    assert "layoutSettled" not in src
    assert not _re.search(r"(?<![A-Za-z_])resized", src), (
        "bare TimelineWidget.resized reference in presenter "
        "(windowResized/on_window_resized dialog wiring is unrelated)"
    )
    assert "_disconnect_view_signals" in destroyed_src, (
        "_on_view_destroyed must disconnect view signals"
    )


def test_no_deleted_timeline_signals_in_thumbnail_wiring():
    """C-A(b): coordinator + service never name resized/layoutSettled."""
    for path in (_THUMB_COORD_PATH, _THUMB_SVC_PATH):
        text = _read_source(path)
        assert "layoutSettled" not in text, path
        assert "resized" not in text, path


def _build_wired_presenter(qapp):
    """Presenter with a fake QObject view; real Qt signals, recorded slots."""
    from PySide6.QtCore import QObject, Signal

    from tabs.image_compare.plugins.video_editor.presenter import (
        VideoEditorPresenter,
    )

    class FakeTimeline(QObject):
        viewportChanged = Signal()
        zoomChanged = Signal(float)
        viewportChangedState = Signal(object)

    class FakeLineEdit(QObject):
        textChanged = Signal(str)
        editingFinished = Signal()

    class FakeView(QObject):
        destroyed = Signal()
        playClicked = Signal(bool)
        playPauseRequested = Signal()
        timelineScrubbed = Signal(int)
        undoClicked = Signal()
        redoClicked = Signal()
        trimClicked = Signal()
        exportClicked = Signal()
        stopExportClicked = Signal()
        widthChanged = Signal(int)
        heightChanged = Signal(int)
        fpsChanged = Signal(int)
        previewScaleChanged = Signal(float)
        aspectRatioLockChanged = Signal(bool)
        fitContentChanged = Signal(bool)
        fitContentFillColorChanged = Signal(object)
        containerChanged = Signal(str)
        windowResized = Signal()

        def __init__(self):
            super().__init__()
            self.timeline = FakeTimeline()
            self.edit_output_dir = FakeLineEdit()
            self.edit_filename = FakeLineEdit()

    calls: list[str] = []

    def _slot(name):
        def _record(*_args):
            calls.append(name)

        return _record

    presenter = VideoEditorPresenter.__new__(VideoEditorPresenter)
    QObject.__init__(presenter)
    view = FakeView()
    presenter.view = view
    presenter.main_controller = None
    presenter.playback_engine = SimpleNamespace()
    presenter.thumbnail_service = SimpleNamespace()
    presenter.playback_coordinator = SimpleNamespace(
        toggle_playback=_slot("toggle_playback"),
        seek_to_frame=_slot("seek_to_frame"),
        undo=_slot("undo"),
        redo=_slot("redo"),
        trim_selection=_slot("trim_selection"),
        on_fps_changed=_slot("on_fps_changed"),
        on_aspect_ratio_lock_changed=_slot("on_aspect_ratio_lock_changed"),
        detach_view=_slot("playback.detach"),
    )
    presenter.preview_coordinator = SimpleNamespace(
        on_width_changed=_slot("on_width_changed"),
        on_height_changed=_slot("on_height_changed"),
        on_preview_scale_changed=_slot("on_preview_scale_changed"),
        on_fit_content_changed=_slot("on_fit_content_changed"),
        on_fit_content_fill_color_changed=_slot(
            "on_fit_content_fill_color_changed"
        ),
        on_window_resized=_slot("on_window_resized"),
        on_view_destroyed=_slot("preview.destroyed"),
        detach_view=_slot("preview.detach"),
    )
    presenter.output_coordinator = SimpleNamespace(
        on_container_changed=_slot("on_container_changed"),
        refresh_unique_output_filename=_slot("refresh_filename"),
        detach_view=_slot("output.detach"),
    )
    presenter.thumbnail_coordinator = SimpleNamespace(
        on_timeline_viewport_changed=_slot("viewport_changed"),
        on_timeline_zoom_changed=_slot("zoom_changed"),
        on_timeline_viewport_state_changed=_slot("viewport_state"),
        detach_view=_slot("thumbs.detach"),
    )
    presenter.export_coordinator = SimpleNamespace(
        stop_export=_slot("stop_export"),
        export_video=lambda *_args: calls.append("export_video"),
        detach_view=_slot("export.detach"),
    )
    return presenter, view, calls


def _emit_all_view_signals(view):
    view.playClicked.emit(False)
    view.playPauseRequested.emit()
    view.timelineScrubbed.emit(3)
    view.undoClicked.emit()
    view.redoClicked.emit()
    view.trimClicked.emit()
    view.exportClicked.emit()
    view.stopExportClicked.emit()
    view.widthChanged.emit(10)
    view.heightChanged.emit(10)
    view.fpsChanged.emit(60)
    view.previewScaleChanged.emit(1.0)
    view.aspectRatioLockChanged.emit(True)
    view.fitContentChanged.emit(True)
    view.fitContentFillColorChanged.emit(object())
    view.containerChanged.emit("mp4")
    view.windowResized.emit()
    view.edit_output_dir.textChanged.emit("x")
    view.edit_filename.editingFinished.emit()
    view.timeline.viewportChanged.emit()
    view.timeline.zoomChanged.emit(1.5)
    view.timeline.viewportChangedState.emit(object())


def test_view_signals_disconnect_stops_all_slots(qapp):
    """C-A(a) runtime: after disconnect, no view/timeline emit reaches us."""
    presenter, view, calls = _build_wired_presenter(qapp)
    presenter._connect_view_signals()

    _emit_all_view_signals(view)
    assert calls, "connected signals must reach coordinator slots"
    assert "viewport_changed" in calls
    assert "zoom_changed" in calls
    assert "viewport_state" in calls

    calls.clear()
    presenter._disconnect_view_signals()
    _emit_all_view_signals(view)
    assert calls == [], (
        f"stale slots survived disconnect: {calls}"
    )


def test_view_destroyed_disconnects_view_signals(qapp):
    """C-A(a) runtime: the destroy path leaves no live slots behind."""
    presenter, view, calls = _build_wired_presenter(qapp)
    presenter._connect_view_signals()
    presenter._on_view_destroyed()

    assert presenter.view is None
    settled = list(calls)
    assert "preview.destroyed" in settled
    _emit_all_view_signals(view)
    assert calls == settled, (
        f"destroy path must disconnect everything else: {calls[len(settled):]}"
    )


def test_frame_count_derives_from_editor_owner(qapp, monkeypatch):
    """C-A(d): service derives through the injected editor-owned provider."""
    service = _live_service(monkeypatch)
    service.generate_thumbnails(
        _FakeRecording(duration=10.5),  # fallback would be ceil(630)+1
        target_count=50,
        priority_indices=[0, 1],
        fps=60,
    )
    assert service._get_frame_count() == 631  # recording fallback formula

    service.set_frame_count_source(lambda: 42)
    assert service._get_frame_count() == 42

    def _boom():
        raise RuntimeError("editor gone")

    service.set_frame_count_source(_boom)
    assert service._get_frame_count() == 631, (
        "provider doubt must fail open to the recording formula"
    )
    service.set_frame_count_source(None)
    assert service._get_frame_count() == 631


def test_coordinator_wires_editor_frame_count(qapp):
    """C-A(d): the coordinator injects editor.get_frame_count as source."""
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    service = SimpleNamespace(
        set_frame_count_source=lambda provider: setattr(
            service, "_frame_count_source", provider
        ),
    )
    editor = SimpleNamespace(get_frame_count=lambda: 77)
    coordinator = ThumbnailCoordinator(
        view=None,
        editor_service=editor,
        playback_engine=SimpleNamespace(),
        thumbnail_service=service,
        emit_thumbnails_updated=lambda _thumbnails: None,
    )
    assert service._frame_count_source == editor.get_frame_count
    assert coordinator.view is None


def test_teardown_clears_sets_and_releases_recording(qapp, monkeypatch):
    """C-A(d): teardown clears pending/generated, drops window+recording."""
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
    assert service._recording is not None
    service.set_visible_window([0, 1, 2])

    service.teardown()

    assert service._pending_indices == set()
    assert service._generated_indices == set()
    assert service._visible_window is None
    assert service._recording is None
    assert service._active_workers == 0

    service._on_thumbnail_generated(
        0, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), generation
    )
    assert emitted == {}, "post-teardown arrival must drop"
    assert service._get_frame_count() == 0, (
        "released recording with no provider reads as empty"
    )


def test_detach_view_cancels_workers_and_clears_baseline(qapp, monkeypatch):
    """C-A(e): detach retires the wave; late add_thumbnail never storms."""
    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    service = _live_service(monkeypatch)
    service.set_thumbnail_disk_cache(None)
    added: list[int] = []
    timeline = SimpleNamespace(
        height=lambda: 200,
        RULER_HEIGHT=24,
        has_snapshots=lambda: True,
        get_total_duration=lambda: 10.0,
        get_pixels_per_second=lambda: 100.0,
        clear_thumbnails=lambda: None,
        add_thumbnail=lambda idx, _px: added.append(idx),
        get_visible_thumbnail_frame_indices=(
            lambda overscan_blocks=0: [0, 1, 2]
        ),
    )
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: _FakeRecording(duration=10.0),
            get_fps=lambda: 60,
            get_frame_count=lambda: 601,
        ),
        playback_engine=SimpleNamespace(),
        thumbnail_service=service,
        emit_thumbnails_updated=lambda _thumbnails: None,
    )
    coordinator.generate_thumbnails()
    assert coordinator._last_visible_indices == [0, 1, 2]

    coordinator.detach_view()

    assert coordinator.view is None
    assert coordinator._last_visible_indices is None
    assert coordinator._last_zoom_level is None
    # Late arrival drops on the retired token; detached view adds nothing.
    coordinator.on_single_thumbnail_ready(0, object())
    assert added == []


def test_optimal_count_prefers_viewport_helpers(qapp, monkeypatch):
    """C-A(e): tile/logical width come from the toolkit viewport module."""
    from tabs.image_compare.plugins.video_editor.presenter_parts import (
        thumbnails as coord_module,
    )

    monkeypatch.setattr(
        coord_module.timeline_viewport,
        "get_base_tile_width",
        lambda _tl: 160.0,
    )
    monkeypatch.setattr(
        coord_module.timeline_viewport,
        "get_logical_width",
        lambda _tl: 4800.0,
    )
    timeline = SimpleNamespace(
        height=lambda: 200,
        RULER_HEIGHT=24,
        has_snapshots=lambda: True,
    )
    coordinator = _coordinator(timeline_indices=[], service=SimpleNamespace())
    coordinator.view = SimpleNamespace(timeline=timeline)

    assert coordinator.calculate_optimal_thumbnail_count() == 32


def test_optimal_count_falls_back_without_viewport_helpers(qapp):
    """C-A(e) fail-open: unreadable viewport helpers keep legacy math."""
    import tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails as coord_module

    def _boom_base(_tl):
        raise RuntimeError("no geometry")

    def _zero_logical(_tl):
        return 0.0

    broken_viewport = SimpleNamespace(
        get_base_tile_width=_boom_base,
        get_logical_width=_zero_logical,
    )
    timeline = SimpleNamespace(
        height=lambda: 200,
        RULER_HEIGHT=24,
        has_snapshots=lambda: True,
        get_total_duration=lambda: 100.0,
        get_pixels_per_second=lambda: 100.0,
    )
    original = coord_module.timeline_viewport
    coord_module.timeline_viewport = broken_viewport
    try:
        coordinator = _coordinator(
            timeline_indices=[], service=SimpleNamespace()
        )
        coordinator.view = SimpleNamespace(timeline=timeline)
        # Legacy math: tile = 176 * 16/9, logical = 100 * 100
        assert coordinator.calculate_optimal_thumbnail_count() == 33
    finally:
        coord_module.timeline_viewport = original
