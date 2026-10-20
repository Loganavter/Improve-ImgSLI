"""Content identity for the video-editor thumbnail pipeline.

Regression for the timeline-class bug (see
improve-imgsli-internal-docs inv-test-suite-state-2026-10-09): a thumbnail for
frame index ``i`` must be rendered from frame ``i``'s snapshot, never a
neighbor's. The wave/generation suites asserted counts and windows only, so an
index -> content swap passed them.

Three layers are covered, all with distinct index-derived colours:

1. Worker seam — ``ThumbnailService._generate_single_thumbnail`` resolves
   ``recording.evaluate_at(i / fps)`` and renders it; the emitted pixels must
   carry frame ``i``'s own colour.
2. Widget seam (blind pocket: the wave tests checked keys/counts, never
   pixels) — the real ``ThumbnailService`` completion -> ``ThumbnailCoordinator``
   -> real ``VideoTimelineWidget`` store, driven from the real visible-window
   refresh. Every *visible* strip rep must decode to its own frame's colour,
   before and after a scroll / zoom remap. ``render.draw_thumbnail_strip``
   resolves each block through ``timeline_viewport.thumbnail_for_rep`` (exact
   match, ``None`` -> theme placeholder), so decoding that pixmap decodes the
   block the user sees.
3. Falsifiability — a ``fill the cache key from a neighbour`` producer and a
   ``bind the neighbour pixmap under key i`` producer must be DETECTED by the
   same content assertion. This keeps the assertion content-true rather than a
   presence check (``pixmap is not None`` would stay green under both).
"""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QScrollArea
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)

from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
    ThumbnailCoordinator,
)
from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
    ThumbnailDiskCache,
    thumbnail_cache_key_for_snap,
)
from tabs.image_compare.plugins.video_editor.services.thumbnails import (
    ThumbnailService,
)
from tabs.image_compare.plugins.video_editor.widgets.timeline import (
    VideoTimelineWidget,
)

_FPS = 10
_THUMB = (160, 90)
# 61 frames at 10 fps. Long enough to scroll away from the initial window.
_FRAMES = 61
# Chrome the real strip needs before the thumbnail store is meaningful: the
# toolkit widget lays out blocks from the viewport width, so it lives in a
# real scroll area exactly like the dialog does.
_VIEWPORT = (900, 300)


def _color_for_index(index: int) -> tuple[int, int, int, int]:
    """Distinct, index-derived colour so a neighbor bind cannot match.

    Offset away from pure black and the theme placeholder greys: index 0 must
    be a valid content colour, not something a missing stripe could fake.
    """
    return (
        (index * 37 + 40) % 256,
        (index * 91 + 60) % 256,
        (index * 53 + 80) % 256,
        255,
    )


def _center_rgba(pixmap: QPixmap) -> tuple[int, int, int, int]:
    image = pixmap.toImage()
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    return (color.red(), color.green(), color.blue(), color.alpha())


def _pixmap_for_index(index: int) -> QPixmap:
    """A solid-thumbnail pixmap of frame ``index``'s colour."""
    image = Image.new("RGBA", _THUMB, _color_for_index(index))
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(
        data, image.width, image.height, QImage.Format.Format_RGBA8888
    )
    return QPixmap.fromImage(qimage.copy())


def _strip_payload(widget, rep_frame: int):
    """Decoded colour of the pixmap the strip paints for ``rep_frame``.

    ``render.draw_thumbnail_strip`` looks each visible block up through
    ``timeline_viewport.thumbnail_for_rep`` (exact match; ``None`` -> the
    theme placeholder). So this returns exactly the content the visible block
    shows: ``None`` means fail-closed placeholder, a colour means that block's
    pixels.
    """
    pixmap = timeline_viewport.thumbnail_for_rep(widget, int(rep_frame))
    if pixmap is None or pixmap.isNull():
        return None
    return _center_rgba(pixmap)


def _painted_block_colors(scroll_area, widget) -> dict[int, tuple]:
    """Decoded pixels of the visible strip, sampled at each block's centre.

    Paints the real scroll-area viewport (the same surface the user sees) and
    samples the block centres derived from the toolkit's own block layout.
    Only meaningful at scroll offset 0: Qt paints a scrolled viewport in
    damage bands, so older content comes from the backing store rather than a
    fresh paint. The scroll/zoom remap is asserted through the store lookup
    above instead.
    """
    canvas = QImage(scroll_area.viewport().size(), QImage.Format.Format_RGB32)
    canvas.fill(Qt.GlobalColor.magenta)
    scroll_area.viewport().render(canvas)

    bar = scroll_area.horizontalScrollBar()
    scroll_x = bar.value()
    content_start = float(widget.LEFT_GUTTER)
    logical = timeline_viewport.get_logical_width(widget)
    viewport_width = timeline_viewport.get_viewport_width(widget)
    blocks = timeline_viewport.strip_block_layout(
        widget,
        content_start_x=content_start,
        start_x=max(content_start, float(scroll_x)),
        end_x=min(
            float(scroll_x + viewport_width - timeline_viewport.right_inset(widget)),
            content_start + logical,
        ),
    )
    y = -timeline_viewport.vertical_scroll_value(widget) + int(widget.STRIP_HEIGHT) // 2
    painted: dict[int, tuple] = {}
    for block_x, block_w, rep in blocks:
        x = int(block_x + block_w / 2 - scroll_x)
        if x < widget.LEFT_GUTTER + 4 or x >= canvas.width():
            # Under the sticky gutter band (partially scrolled block).
            continue
        color = canvas.pixelColor(x, y)
        painted[rep] = (color.red(), color.green(), color.blue(), color.alpha())
    return painted


def _assert_visible_thumbnails_are_content_true(widget) -> list[int]:
    """Every visible rep decodes to its own frame colour, never a neighbor's."""
    reps = widget.get_visible_thumbnail_frame_indices(0)
    assert reps, "no visible strip blocks — the harness has no window to check"
    for rep in reps:
        payload = _strip_payload(widget, rep)
        assert payload == _color_for_index(rep), (
            f"visible block rep={rep} shows {payload}, "
            f"expected its own {_color_for_index(rep)}"
        )
        for other in (rep - 1, rep + 1):
            if 0 <= other < _FRAMES:
                assert payload != _color_for_index(other), (
                    f"visible block rep={rep} shows neighbor frame {other}'s "
                    f"colour {_color_for_index(other)}"
                )
    return reps


# ---------------------------------------------------------------------------
# 1. Worker seam: index -> snapshot -> rendered pixels.
# ---------------------------------------------------------------------------


class _TimestampRecording:
    """``evaluate_at(t)`` returns ``t``; the frame colour follows from ``t``."""

    def get_duration(self) -> float:
        return 30.0

    def evaluate_at(self, timestamp: float):
        return float(timestamp)


def _render_snapshot(snap, target_w, target_h, *, auto_crop=False):
    # snap is the frame timestamp; recover the frame index and paint its colour.
    index = int(round(float(snap) * _FPS))
    return Image.new("RGBA", (target_w * 2, target_h * 2), _color_for_index(index))


def test_thumbnail_renders_its_own_frame_not_a_neighbor(qapp):
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    recording = _TimestampRecording()

    for index in (0, 3, 7, 11, 25):
        rendered = service._generate_single_thumbnail(
            index,
            _THUMB,
            False,
            1.0,
            _FPS,
            None,
            recording=recording,
            render_snapshot=_render_snapshot,
        )
        assert rendered is not None, f"index {index} produced no thumbnail"
        assert rendered.size == _THUMB
        got = rendered.convert("RGBA").getpixel(
            (rendered.size[0] // 2, rendered.size[1] // 2)
        )
        assert got == _color_for_index(index), (
            f"index {index} rendered a neighbor's frame: {got}"
        )


def test_missing_render_capture_fails_closed(qapp):
    """No queue-time capture -> miss, never a render from live params."""
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(None)
    assert (
        service._generate_single_thumbnail(3, _THUMB, False, 1.0, _FPS, None)
        is None
    )


# ---------------------------------------------------------------------------
# 2. Widget seam: service completion -> coordinator -> real timeline widget.
# ---------------------------------------------------------------------------


class _IndexRecording:
    """``evaluate_at(t)`` maps the timestamp back to the frame index."""

    def get_duration(self) -> float:
        return (_FRAMES - 1) / _FPS

    def evaluate_at(self, timestamp: float):
        return int(round(float(timestamp) * _FPS))


def _render_index_frame(snap, target_w, target_h, *, auto_crop=False):
    return Image.new(
        "RGBA", (target_w * 2, target_h * 2), _color_for_index(int(snap))
    )


class _EditorService:
    def __init__(self, recording):
        self._recording = recording

    def get_current_recording(self):
        return self._recording

    def get_fps(self) -> int:
        return _FPS

    def get_frame_count(self) -> int:
        return _FRAMES


class _TimelineHarness:
    """Real widget + real service/coordinator, workers run synchronously."""

    def __init__(self, qapp):
        self.qapp = qapp
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.snapshots = [
            SimpleNamespace(timestamp=i / _FPS, frame_index=i)
            for i in range(_FRAMES)
        ]
        self.widget = VideoTimelineWidget(self.snapshots, store=None)
        self.scroll.setWidget(self.widget)
        self.scroll.resize(*_VIEWPORT)
        self.scroll.show()
        qapp.processEvents()
        self.widget.set_data(
            self.snapshots, fps=_FPS, duration=(_FRAMES - 1) / _FPS
        )
        self.widget.resize(880, 240)

        self.service = ThumbnailService()
        self.service.set_thumbnail_disk_cache(None)
        self.service.set_snapshot_renderer(_render_index_frame)
        # One worker at a time, completed inline: the same signal path the pool
        # uses, minus thread scheduling (timing is not under test).
        self.service._thread_pool.start = lambda worker, priority=0: worker.run()

        self.editor = _EditorService(_IndexRecording())
        self.service.set_frame_count_source(self.editor.get_frame_count)
        self.coordinator = ThumbnailCoordinator(
            view=SimpleNamespace(timeline=self.widget),
            editor_service=self.editor,
            playback_engine=SimpleNamespace(get_current_frame=lambda: 0),
            thumbnail_service=self.service,
            emit_thumbnails_updated=lambda _thumbnails: None,
        )
        self.service.thumbnailReady.connect(
            lambda index, pixmap: self.coordinator.on_single_thumbnail_ready(
                index, pixmap
            )
        )
        self.service.thumbnailsGenerated.connect(
            self.coordinator.on_thumbnails_generated
        )

        self.widget.fit_view()
        self.widget.set_zoom(1.0)
        self.widget.update_layout_width()
        qapp.processEvents()

    def generate(self):
        self.coordinator.generate_thumbnails()
        self.qapp.processEvents()

    def visible(self) -> list[int]:
        return self.widget.get_visible_thumbnail_frame_indices(0)

    def scroll_to(self, value: int):
        self.scroll.horizontalScrollBar().setValue(int(value))
        self.qapp.processEvents()
        # The presenter wires viewportChangedState straight to this refresh
        # (no debounce) — call the same entry so the remap is deterministic.
        self.coordinator.on_timeline_viewport_state_changed()
        self.qapp.processEvents()

    def zoom_to(self, zoom: float):
        self.widget.set_zoom(float(zoom))
        self.widget.update_layout_width()
        self.qapp.processEvents()
        self.coordinator.on_timeline_viewport_state_changed()
        self.qapp.processEvents()

    def close(self):
        self.coordinator.cleanup()
        self.widget.close()
        self.scroll.close()
        self.scroll.deleteLater()


def test_visible_strip_thumbnails_carry_their_own_frame(qapp):
    harness = _TimelineHarness(qapp)
    try:
        harness.generate()
        reps = _assert_visible_thumbnails_are_content_true(harness.widget)
        # Literal pixels: the strip painted through the real viewport carries
        # each block's own frame colour (not a neighbour's, not the theme
        # placeholder). Only the unscrolled viewport is damage-deterministic.
        painted = _painted_block_colors(harness.scroll, harness.widget)
        assert len(painted) >= 3, f"only {len(painted)} blocks painted"
        assert set(painted) <= set(reps)
        for rep, color in painted.items():
            assert color == _color_for_index(rep), (
                f"painted block rep={rep} is {color}, "
                f"expected its own {_color_for_index(rep)}"
            )
        # The wave-discipline bound stays a PERF assertion: the initial wave
        # covers the visible window (plus the generation margin), not all 61.
        assert len(reps) < _FRAMES
        assert len(harness.widget._thumbnails) <= len(reps) + 4
    finally:
        harness.close()


def test_scroll_and_zoom_remap_never_cross_binds_thumbnail_content(qapp):
    """Pan then zoom: every newly visible rep re-binds to its own frame."""
    harness = _TimelineHarness(qapp)
    try:
        harness.generate()
        initial = _assert_visible_thumbnails_are_content_true(harness.widget)

        harness.scroll_to(900)
        scrolled = _assert_visible_thumbnails_are_content_true(harness.widget)
        assert set(scrolled) != set(initial), (
            "scroll did not move the visible window — remap untested"
        )
        # The scrolled-to frames were never in the initial wave, so their
        # pixels can only come from the scroll refresh's index-addressed queue.
        for rep in scrolled:
            if rep not in initial:
                assert _strip_payload(harness.widget, rep) == _color_for_index(rep)

        harness.zoom_to(0.75)
        zoomed = _assert_visible_thumbnails_are_content_true(harness.widget)
        assert set(zoomed) != set(scrolled), (
            "zoom did not remap the rep grid — remap untested"
        )
        # Zoom keeps the in-flight wave alive (Z4: geometry, not content), so
        # re-resolved reps must still read their own pixmap, never a neighbor.
        for rep in zoomed:
            payload = _strip_payload(harness.widget, rep)
            assert payload == _color_for_index(rep), (
                f"zoom remap bound rep={rep} to {payload}"
            )
    finally:
        harness.close()


# ---------------------------------------------------------------------------
# 3. Fail-closed and falsifiability: the assertions above must see bad pixels.
# ---------------------------------------------------------------------------


def test_bad_producer_neighbor_bind_is_detected_by_the_same_assertion(qapp):
    """Widget store poisoned with frame i+1's pixmap under key i: DETECTED.

    This is the falsification story for the widget-seam test: a presence-only
    check (``thumbnail_for_rep(...) is not None``) stays green here, the
    content assertion goes red — so the green run above is evidence about
    pixels, not about keys being present.
    """
    harness = _TimelineHarness(qapp)
    try:
        harness.generate()
        rep = harness.visible()[2]
        neighbor = rep + 1

        harness.widget.add_thumbnail(rep, _pixmap_for_index(neighbor))

        payload = _strip_payload(harness.widget, rep)
        assert payload == _color_for_index(neighbor), (
            "the poisoned store did not surface the neighbor's pixels"
        )
        assert payload != _color_for_index(rep), (
            "content assertion accepted the neighbor's pixels"
        )
        # Same falsification for the painted-pixel assertion: the visible
        # block really shows the neighbor colour on the painted surface.
        painted = _painted_block_colors(harness.scroll, harness.widget)
        assert painted.get(rep) == _color_for_index(neighbor)
        assert painted.get(rep) != _color_for_index(rep)
        # Untouched reps remain content-true (the poison is index-local).
        for other in harness.visible():
            if other != rep:
                assert _strip_payload(harness.widget, other) == _color_for_index(
                    other
                )
    finally:
        harness.close()


class _StatSnapshotRecording:
    """Recording whose snapshots carry stat-able source paths (disk-cache key)."""

    def __init__(self, source_path: str):
        self._source = source_path
        self._snaps = {}

    def _snap(self, index: int):
        if index not in self._snaps:
            self._snaps[index] = SimpleNamespace(
                timestamp=index / _FPS,
                frame_index=index,
                image1_path=self._source,
                image2_path=self._source,
                name1="a",
                name2="b",
                viewport_state=f"viewport-{index}",
                settings_state=f"settings-{index}",
            )
        return self._snaps[index]

    def get_duration(self) -> float:
        return (_FRAMES - 1) / _FPS

    def evaluate_at(self, timestamp: float):
        return self._snap(int(round(float(timestamp) * _FPS)))


def test_poisoned_disk_cache_key_serves_neighbor_content_not_own(
    qapp, tmp_path
):
    """Key i filled from frame i+1 (bad producer): the assertion DETECTS it.

    Proves the content check is not satisfiable by any cache hit: the hit is
    served without rendering, and its decoded pixels are the neighbor's — so a
    green content run means the producer rendered (or cached) its own frame.
    """
    source = tmp_path / "src.png"
    Image.new("RGB", (32, 18), (10, 20, 30)).save(str(source))
    recording = _StatSnapshotRecording(str(source))
    cache = ThumbnailDiskCache(str(tmp_path / "thumbs"))
    index = 7
    snap = recording.evaluate_at(index / _FPS)
    key = thumbnail_cache_key_for_snap(
        snap,
        index=index,
        fps=_FPS,
        auto_crop=False,
        thumbnail_size=_THUMB,
        render_scale=1.0,
    )
    assert key is not None, "disk-cache key unavailable for the fixture snapshot"
    assert cache.put(key, Image.new("RGBA", _THUMB, _color_for_index(index + 1)))

    rendered: list[int] = []

    def _renderer(snap, target_w, target_h, *, auto_crop=False):
        rendered.append(int(snap.frame_index))
        image = Image.new(
            "RGBA", (target_w * 2, target_h * 2), _color_for_index(snap.frame_index)
        )
        return image

    service = ThumbnailService()
    service.set_thumbnail_disk_cache(cache)
    service.set_snapshot_renderer(_renderer)
    service._thread_pool.start = lambda worker, priority=0: worker.run()
    emitted: list[tuple[int, QPixmap]] = []
    service.thumbnailReady.connect(
        lambda emitted_index, pixmap: emitted.append((emitted_index, pixmap))
    )

    service.generate_thumbnails(
        recording, target_count=1, priority_indices=[index], fps=_FPS
    )

    assert rendered == [], "cache hit must not start a worker"
    assert [emitted_index for emitted_index, _ in emitted] == [index]
    payload = _center_rgba(emitted[0][1])
    assert payload == _color_for_index(index + 1), (
        f"cache hit at key {index} did not surface the stored neighbor pixels: "
        f"{payload}"
    )
    assert payload != _color_for_index(index), (
        "content assertion accepted a neighbor-frame cache entry as frame "
        f"{index}"
    )


def test_missing_thumbnail_rep_stays_fail_closed_never_a_neighbor(qapp):
    """Evicted/never-rendered rep: placeholder, never a neighbor's pixmap."""
    harness = _TimelineHarness(qapp)
    try:
        harness.generate()
        reps = harness.visible()
        target = reps[len(reps) // 2]

        # Keep every visible neighbor, drop only ``target`` — the shape of a
        # prune/miss with a populated store around it.
        harness.widget.clear_thumbnails()
        for rep in reps:
            if rep != target:
                harness.widget.add_thumbnail(rep, _pixmap_for_index(rep))

        assert timeline_viewport.thumbnail_for_rep(harness.widget, target) is None, (
            "missing rep resolved to a pixmap (fail-closed lookup broken)"
        )
        assert _strip_payload(harness.widget, target) is None
        for other in reps:
            if other != target:
                assert _strip_payload(harness.widget, other) == _color_for_index(
                    other
                ), f"neighbor rep={other} lost its own content"
    finally:
        harness.close()
