"""Video frame-count parity: one source for editor/export/playback.

Dogma: ``editor.frame_count_for_duration`` (``ceil(duration * fps) + 1``) is
the single frame-count source consumed by ``VideoEditorService``,
``VideoExporterService._build_export_job`` and ``PlaybackEngine``
(total/range). No test here stubs ``get_frame_count`` -- every count comes
from a real ``KeyframedRecording`` built from distinguishable snapshots.

Content identity (not counts alone): frame index ``i`` carries time
``i / fps``; each snapshot carries a distinct ``name1`` payload and the
frame resolves back to exactly that payload.
"""
from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from core.store import Store
from tabs.image_compare.plugins.video_editor.services.editor import (
    VideoEditorService,
    frame_count_for_duration,
)
from tabs.image_compare.plugins.video_editor.services.keyframing import (
    KeyframedRecording,
)
from tabs.image_compare.plugins.video_editor.services.keyframing.types import FrameSnapshot
from tabs.image_compare.plugins.video_editor.services.playback import PlaybackEngine
from ui.canvas_infra.scene.feature_state_api import execute_feature_command

_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


@pytest.fixture(autouse=True)
def _register_image_compare_canvas_features():
    from tabs.image_compare.tab import ImageCompareTab
    from tabs.registry import get_shared_tab_registry

    ImageCompareTab().register_canvas_features()
    registry = get_shared_tab_registry()
    previous_active = registry._active_session_type
    registry._active_session_type = "image_compare"
    try:
        yield
    finally:
        registry._active_session_type = previous_active


def _recording(*, fps=60, n_frames=121):
    """Real recording: snapshots on every frame grid instant, distinct payloads."""
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    try:
        execute_feature_command(store, "magnifier", "add_instance")
    except Exception:
        pass
    snapshots = [
        FrameSnapshot(
            timestamp=float(i) / float(fps),
            viewport_state=store.viewport,
            settings_state=store.settings,
            image1_path=None,
            image2_path=None,
            name1=f"shot-{i}",
            name2=f"other-{i}",
        )
        for i in range(n_frames)
    ]
    recording = KeyframedRecording.from_snapshots(snapshots, fps=fps)
    return recording, store


def test_single_source_matches_ceil_plus_one():
    recording, _store = _recording(fps=60, n_frames=121)
    duration = recording.get_duration()
    assert duration == pytest.approx(2.0)
    assert frame_count_for_duration(duration, 60) == 121
    # Non-integer duration keeps the tail instant instead of flooring it away.
    assert frame_count_for_duration(0.555, 60) == max(1, math.ceil(0.555 * 60) + 1) == 35
    assert frame_count_for_duration(0.0, 60) == 1
    assert frame_count_for_duration(-1.0, 60) == 1


def test_editor_export_playback_agree_on_real_recording():
    fps, n_frames = 60, 121
    recording, store = _recording(fps=fps, n_frames=n_frames)
    duration = recording.get_duration()
    expected = math.ceil(duration * fps) + 1
    assert expected == n_frames

    editor = VideoEditorService(recording, fps=fps)
    assert editor.get_frame_count() == expected

    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    exporter = VideoExporterService(recorder=recording, store=store, main_controller=None)
    job = exporter._build_export_job(
        recording,
        (320, 240),
        fps,
        {"container": "mp4", "output_dir": str(os.getcwd()), "file_name": "parity_probe_tmp"},
    )
    try:
        assert job.total_frames == expected == editor.get_frame_count()
        # Frame-time parity: export sample times equal editor frame times,
        # index by index, with the tail landing exactly on duration.
        export_times = [float(i) / float(job.fps) for i in range(job.total_frames)]
        editor_times = [editor.get_time_for_frame(i) for i in range(editor.get_frame_count())]
        assert export_times == editor_times
        assert export_times[-1] == pytest.approx(duration)
        assert all(b > a for a, b in zip(export_times, export_times[1:]))
    finally:
        try:
            os.remove(job.output_path)
        except OSError:
            pass

    _app()
    engine = PlaybackEngine(fps=fps)
    engine.set_total_frames(editor.get_frame_count())
    engine.set_range(0, expected - 1)
    assert engine._range == (0, expected - 1)
    assert engine._total_frames == expected


def test_frame_index_resolves_distinct_payload():
    """payload(i) == content(i) under the engine's right-closed hold.

    ``evaluate_channel`` returns the previous keyframe's value on an exact
    timestamp hit with ``hold`` interpolation, so frame ``i`` (time ``i/fps``)
    resolves to snapshot ``0`` for ``i == 0`` else snapshot ``i - 1``. Each
    frame maps to exactly one snapshot payload -- deterministic per index,
    never a blend -- and every snapshot's payload is observed on some frame.
    """
    fps, n_frames = 30, 31
    recording, _store = _recording(fps=fps, n_frames=n_frames)
    editor = VideoEditorService(recording, fps=fps)
    assert editor.get_frame_count() == n_frames
    seen = set()
    for i in range(n_frames):
        assert editor.get_time_for_frame(i) == pytest.approx(float(i) / float(fps))
        snap = editor.get_snapshot_at(i)
        want = 0 if i == 0 else i - 1
        assert snap.name1 == f"shot-{want}"
        assert snap.name2 == f"other-{want}"
        seen.add(snap.name1)
    assert seen == {f"shot-{i}" for i in range(n_frames - 1)}


def test_sparse_recording_holds_left_value_mid_interval():
    """Sparse case: a mid-interval frame holds the left payload, never a gap."""
    fps = 30
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    snapshots = [
        FrameSnapshot(
            timestamp=t,
            viewport_state=store.viewport,
            settings_state=store.settings,
            image1_path=None,
            image2_path=None,
            name1=name,
            name2=name,
        )
        for t, name in ((0.0, "sparse-A"), (1.0, "sparse-B"))
    ]
    recording = KeyframedRecording.from_snapshots(snapshots, fps=fps)
    editor = VideoEditorService(recording, fps=fps)
    assert editor.get_frame_count() == 31
    mid = editor.get_snapshot_at(15)
    assert mid.name1 == "sparse-A"
    tail = editor.get_snapshot_at(30)
    assert tail.name1 == "sparse-A"  # right-closed hold: B starts after its knot
    assert mid is not None and tail is not None


def test_playback_range_clamped_to_total():
    _app()
    engine = PlaybackEngine(fps=60)
    engine.set_total_frames(121)
    # Stale view selection past the tail clamps instead of playing wrong-time.
    engine.set_range(0, 500)
    assert engine._range == (0, 120)
    engine.set_range(-5, 10**6)
    assert engine._range == (0, 120)
    engine.set_range(200, 300)
    assert engine._range == (120, 120)
    # Shrinking the timeline pulls a wide range back inside.
    engine.set_range(0, 120)
    engine.set_total_frames(10)
    assert engine._range == (0, 9)
    engine.set_current_frame(500)
    assert engine.get_current_frame() == 9
