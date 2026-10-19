"""Rendered-pixel content identity for the video-editor PREVIEW pane.

The other two content-identity surfaces are already covered:

* timeline strip per-index colour — ``test_thumbnail_content_identity.py``;
* export per-frame payload — ``test_video_export_robustness.py``.

The preview pane only had a *cache-key sensitivity* test
(``test_video_editor_preview_contracts.py::test_preview_keys_change_with_snapshot_content``),
which proves keys differ but never that the pixels the preview surface gets
belong to the frame the user is looking at. This module closes that hole by
driving the real ``PreviewCoordinator`` (schedule -> prepare -> apply) with a
recording whose frame payload encodes the frame index and asserting the
payload handed to the canvas for frame ``i`` is frame ``i``'s own colour.

Async failure modes covered:

* a late/stale prepare result arriving after a fresher one must be dropped by
  the ``_render_task_id`` guard, never replace the newer pixels;
* a sparse/evicted frame (no snapshot) must leave a placeholder (cleared
  surface), never the previous neighbour's payload;
* a seek must remap the frame cache: a resize refit pulse before the new
  prepare lands, and a seek back to an earlier frame, must never keep binding
  the old frame's plan to the new frame index.

Production bug found by the sparse-frame case (red before the fix): with
frame 2 rendered (payload = ``(74, 182, 106, 255)``) and frame 3 having no
snapshot, ``do_update_preview_heavy`` returned before invalidating
``_preview_frame_cache`` / ``_last_render_params`` and before clearing the
canvas. The cached plan remained bound to frame 2's ``prepare_key``
(``_preview_frame_cache["prepare_key"]``) and frame 2's ``(74, 182, 106, 255)``
pixels stayed on screen while the playhead showed frame 3 (whose own colour
would be ``(111, 17, 159, 255)``). Fix: the missing-snapshot branch clears the
preview surface and drops the frame cache / last-render params.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QObject

from tabs.image_compare.plugins.video_editor.presenter_parts import (
    preview as preview_module,
)
from tabs.image_compare.plugins.video_editor.presenter_parts.preview import (
    PreviewCoordinator,
)

_FPS = 10
_PREVIEW = (100, 50)


def _frame_color(index: int) -> tuple[int, int, int, int]:
    """Distinct index-derived colour so a neighbour bind cannot match."""
    return ((index * 37) % 256, (index * 91) % 256, (index * 53) % 256, 255)


def _center(image: Image.Image) -> tuple[int, int, int, int]:
    return image.convert("RGBA").getpixel((image.width // 2, image.height // 2))


class _FrameRecording:
    """``evaluate_at(t)`` maps the timestamp back to the frame index.

    ``missing`` indices are sparse (evicted/never materialized) and evaluate
    to ``None`` — exactly what a recording with a hole returns.
    """

    def __init__(self, *, total_frames: int = 12, missing: set[int] | None = None):
        self.total_frames = total_frames
        self.missing = set(missing or ())

    def get_duration(self) -> float:
        return float(self.total_frames) / _FPS

    def evaluate_at(self, timestamp: float):
        index = int(round(float(timestamp) * _FPS))
        if index in self.missing:
            return None
        return SimpleNamespace(
            image1_path="/rec/a.png",
            image2_path="/rec/b.png",
            name1="a",
            name2="b",
            timestamp=index / _FPS,
            # Stable per-index state objects keep the cache key stable for a
            # repeated render of the same frame (the cache-hit path).
            viewport_state=SimpleNamespace(index=index, render_config=None, view_state=None),
            settings_state=SimpleNamespace(index=index),
        )


class _EditorService:
    def __init__(self, recording: _FrameRecording):
        self._recording = recording

    def get_snapshot_at(self, index: int):
        return self._recording.evaluate_at(index / _FPS)


class _PreviewExporter:
    """Test double for the export renderer; encodes the frame index in pixels."""

    def __init__(self, recording: _FrameRecording):
        self.recording = recording
        self.prepare_calls: list[int] = []

    def prepare_snapshot_canvas_frame(self, snap, out_w, out_h, **kwargs):
        index = int(round(float(snap.timestamp) * _FPS))
        self.prepare_calls.append(index)
        image = Image.new("RGBA", _PREVIEW, _frame_color(index))
        plan = SimpleNamespace(
            canvas_w=out_w,
            canvas_h=out_h,
            image1=image,
            image2=image,
            fill_rgba=(0, 0, 0, 0),
            render_scene=SimpleNamespace(overlay_clip_rect=(0, 0, out_w, out_h)),
            image_is_padded_composite=False,
        )
        return SimpleNamespace(
            plan=plan,
            store=SimpleNamespace(index=index),
            output_width=out_w,
            output_height=out_h,
            image_dest_x=0,
            image_dest_y=0,
            debug={},
        )


class _RecordingCanvas:
    """Preview surface double recording what the plan applicator uploaded."""

    def __init__(self):
        self.rendered_payload = None
        self.rendered_store = None
        self._preview_source_key = None
        self._use_plan_fill_clear = True
        self.applied: list[tuple] = []
        self.updates = 0
        self.clears = 0
        self._read_only = False

    def set_read_only(self, enabled):
        self._read_only = bool(enabled)

    def devicePixelRatioF(self):
        return 1.0

    def update(self):
        self.updates += 1

    def clear(self):
        self.clears += 1
        self.rendered_payload = None
        self.rendered_store = None


class _DeferredPreparePool:
    """Stand-in for the single-thread prepare pool.

    Workers are captured instead of run so a test can deliver results in any
    order (the real pool is 1-thread, but the completion callback contract
    must hold for out-of-order delivery too).
    """

    def __init__(self):
        self.pending: list = []

    def start(self, worker):
        self.pending.append(worker)

    def take(self, count: int = 1):
        taken, self.pending = self.pending[:count], self.pending[count:]
        return taken


class _Harness:
    def __init__(self, recording: _FrameRecording, monkeypatch):
        self.recording = recording
        self.editor_service = _EditorService(recording)
        self.exporter = _PreviewExporter(recording)
        self.canvas = _RecordingCanvas()
        self.current_frame = 0
        self.view = SimpleNamespace(
            preview_label=self.canvas,
            get_preview_size=lambda: _PREVIEW,
            fit_content_fill_color=None,
        )
        self.playback_engine = SimpleNamespace(
            is_playing=lambda: False,
            get_current_frame=lambda: self.current_frame,
        )
        self.timer_parent = QObject()
        self.coordinator = PreviewCoordinator(
            view=self.view,
            export_controller=SimpleNamespace(video_exporter=self.exporter),
            playback_engine=self.playback_engine,
            model=SimpleNamespace(width=_PREVIEW[0], height=_PREVIEW[1], aspect_ratio_locked=False),
            editor_service=self.editor_service,
            timer_parent=self.timer_parent,
            emit_preview_ready=lambda: None,
        )
        self.pool = _DeferredPreparePool()
        self.coordinator._prepare_pool = self.pool
        self._test_timer_parent = self.timer_parent

        def _capture_apply(canvas, plan, **kwargs):
            canvas.applied.append((plan, kwargs))
            canvas.rendered_payload = plan.image1
            canvas.rendered_store = kwargs.get("store")

        monkeypatch.setattr(preview_module, "apply_canvas_render_plan", _capture_apply)

    def seek(self, index: int):
        self.current_frame = index

    def snapshot(self, index: int):
        return self.editor_service.get_snapshot_at(index)

    def deliver_all(self):
        while True:
            workers = self.pool.take()
            if not workers:
                return
            for worker in workers:
                worker.run()

    def render_current(self, *, deliver: bool = True):
        self.coordinator.do_update_preview_heavy()
        if deliver:
            self.deliver_all()

    def rendered_color(self):
        payload = self.canvas.rendered_payload
        return None if payload is None else _center(payload)

    def teardown(self):
        self.coordinator.on_view_destroyed()


def test_preview_renders_its_own_frame_payload(monkeypatch):
    """Frame i's colour reaches the preview surface for frame i (not i-1/i+1)."""
    harness = _Harness(_FrameRecording(), monkeypatch)

    for index in (0, 3, 7, 2, 11):
        harness.seek(index)
        harness.render_current()
        got = harness.rendered_color()
        assert got == _frame_color(index), (
            f"preview on frame {index} rendered {got}, "
            f"expected its own {_frame_color(index)}"
        )
        for other in (index - 1, index + 1):
            if 0 <= other < harness.recording.total_frames:
                assert got != _frame_color(other)

    harness.teardown()


def test_late_stale_prepare_never_replaces_fresh_payload(monkeypatch):
    """A stale result arriving after a fresher one is dropped by task id."""
    harness = _Harness(_FrameRecording(), monkeypatch)

    # Two in-flight prepares, as an out-of-order completion would deliver:
    # frame 0 requested first (task 1), frame 1 requested later (task 2).
    harness.coordinator._render_task_id = 1
    assert harness.coordinator.render_preview_gpu(harness.snapshot(0)) is False
    stale_worker = harness.pool.take()[0]

    harness.coordinator._render_task_id = 2
    assert harness.coordinator.render_preview_gpu(harness.snapshot(1)) is False
    fresh_worker = harness.pool.take()[0]

    fresh_worker.run()
    assert harness.rendered_color() == _frame_color(1)

    stale_worker.run()  # late frame 0 result
    assert harness.rendered_color() == _frame_color(1), (
        "late frame 0 result replaced frame 1's payload"
    )
    assert harness.canvas.rendered_store.index == 1

    harness.teardown()


def test_missing_snapshot_shows_placeholder_not_neighbour(monkeypatch):
    """Sparse frame: the previous frame's pixels must not stay on screen."""
    harness = _Harness(_FrameRecording(missing={3}), monkeypatch)

    harness.seek(2)
    harness.render_current()
    assert harness.rendered_color() == _frame_color(2)

    harness.seek(3)  # evicted / never materialized
    harness.render_current()

    assert harness.rendered_color() is None, (
        "frame 3 has no snapshot but the preview still shows frame 2's payload"
    )
    assert harness.canvas.clears == 1
    assert harness.coordinator._preview_frame_cache is None, (
        "missing-frame path left frame 2's plan cached (cross-frame binding)"
    )
    assert harness.coordinator._last_render_params == (None, None, None)

    # Recovering to a real frame must render again (the cache was dropped,
    # not merely hidden behind a one-shot flag).
    harness.seek(2)
    harness.render_current()
    assert harness.rendered_color() == _frame_color(2)

    harness.teardown()


def test_seek_remaps_frame_cache_without_cross_binding(monkeypatch):
    """Resize-refit after a seek must not pin the old frame; render follows."""
    harness = _Harness(_FrameRecording(), monkeypatch)

    harness.seek(0)
    harness.render_current()
    assert harness.rendered_color() == _frame_color(0)
    key_for_frame_0 = harness.canvas._preview_source_key

    # Seek to frame 2 while a resize settle pulse is still in flight: the
    # refit path re-applies the cached plan before the new prepare lands.
    harness.seek(2)
    harness.coordinator._refit_cached_preview_to_widget()
    harness.render_current()

    assert harness.rendered_color() == _frame_color(2)
    assert harness.canvas._preview_source_key != key_for_frame_0, (
        "frame 2 was bound to frame 0's cached source key"
    )
    # Seek back: the old frame's pixels must be re-rendered, not left over.
    harness.seek(0)
    harness.render_current()
    assert harness.rendered_color() == _frame_color(0)

    harness.teardown()
