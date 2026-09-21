"""Video export robustness: skip accounting, bounded rendezvous, cache keys.

- Silent frame drops shorten the stream: every skip is counted and loud,
  and past the budget the export aborts instead of producing a short video.
- A wedged ffmpeg past cancel must hang neither the producer (blocking put
  on a full queue) nor teardown (unbounded join): both are bounded.
- Bounds cache key carries a content fingerprint (length-plus-tail alone
  aliases swapped-middle recordings); prescale cache key carries auto_crop
  and the interpolation method (settings-only changes recompute).
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from tabs.image_compare.plugins.video_editor.services.video_export.render_loop import (
    VideoRenderLoop,
)

_APP = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _frame_image(w=8, h=4, color=(10, 20, 30, 255)):
    return Image.new("RGBA", (w, h), color)


class _FakeStdin:
    def __init__(self, delay_s=0.0):
        self.written: list[bytes] = []
        self.delay_s = delay_s

    def write(self, payload: bytes):
        # Record first: a slow encoder still takes the bytes, then stalls.
        self.written.append(bytes(payload))
        if self.delay_s:
            time.sleep(self.delay_s)


class _FakeProcess:
    def __init__(self, delay_s=0.0):
        self.stdin = _FakeStdin(delay_s=delay_s)
        self.returncode = 0

    def poll(self):
        return None


def _exporter(*, fail_first=0, cancel_after_calls=None):
    """Fake exporter: first ``fail_first`` renders drop, then succeed."""
    state = {"calls": 0}

    def render_snapshot_to_pil(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] <= fail_first:
            return None
        return _frame_image()

    def is_cancel_requested():
        if cancel_after_calls is not None and state["calls"] >= cancel_after_calls:
            return True
        return False

    return (
        SimpleNamespace(
            main_controller=None,
            render_snapshot_to_pil=render_snapshot_to_pil,
            _drain_last_render_debug=lambda: {},
            _last_render_backend="cpu",
            is_cancel_requested=is_cancel_requested,
        ),
        state,
    )


def _job(total_frames):
    recording = SimpleNamespace(
        evaluate_at=lambda t: SimpleNamespace(timestamp=t),
    )
    return SimpleNamespace(
        recording=recording,
        width=8,
        height=4,
        fps=60,
        total_frames=total_frames,
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
        fill_rgba=(0, 0, 0, 0),
    )


def test_max_skip_abort_is_loud():
    exporter, _state = _exporter(fail_first=10**9)
    loop = VideoRenderLoop(exporter)
    job = _job(20)
    with pytest.raises(RuntimeError, match="refusing to produce a short stream"):
        loop.render(_FakeProcess(), job)
    # Aborted right past the budget: max(10, 5% of 20) == 10.
    assert loop.skipped_frames == 11


def test_tolerated_skips_are_counted_and_stream_stays_full():
    exporter, _state = _exporter(fail_first=3)
    loop = VideoRenderLoop(exporter)
    job = _job(20)
    process = _FakeProcess()
    assert loop.render(process, job) is False
    assert loop.skipped_frames == 3
    # 17 distinguishable payloads reached the writer, none empty.
    assert len(process.stdin.written) == 17
    assert {len(p) for p in process.stdin.written} == {8 * 4 * 4}
    assert all(len(p) > 0 for p in process.stdin.written)


def test_bounded_rendezvous_past_cancel(monkeypatch):
    """Hung writer + cancel: render() returns instead of wedging."""
    monkeypatch.setattr(VideoRenderLoop, "_ENQUEUE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(VideoRenderLoop, "_WRITER_JOIN_TIMEOUT_S", 0.3)
    exporter, _state = _exporter(fail_first=0, cancel_after_calls=4)
    loop = VideoRenderLoop(exporter)
    job = _job(30)
    process = _FakeProcess(delay_s=5.0)
    started = time.monotonic()
    assert loop.render(process, job) is True
    assert time.monotonic() - started < 4.0
    assert process.stdin.written, "no frame reached the writer before cancel"


def _snap(path1, path2, ts):
    from tabs.image_compare.plugins.video_editor.services.keyframing.types import (
        FrameSnapshot,
    )

    return FrameSnapshot(
        timestamp=ts,
        viewport_state=None,
        settings_state=None,
        image1_path=path1,
        image2_path=path2,
        name1=path1,
        name2=path2,
    )


def _bounds_service(tmp_path):
    _app()
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VideoExporterService,
    )

    store = SimpleNamespace(
        settings=SimpleNamespace(export_default_dir=str(tmp_path))
    )
    return VideoExporterService(
        recorder=SimpleNamespace(snapshots=[]), store=store, main_controller=None
    )


def _counting_bounds(service):
    from tabs.image_compare.plugins.video_editor.services.video_export.models import (
        GlobalCanvasBounds,
    )

    calls = {"n": 0}

    def calculate(materialized, auto_crop=False):
        calls["n"] += 1
        return GlobalCanvasBounds(
            pad_left=0,
            pad_right=0,
            pad_top=0,
            pad_bottom=calls["n"],
            base_width=64,
            base_height=48,
        )

    service._bounds_analyzer = SimpleNamespace(calculate=calculate)
    return calls


def test_bounds_key_varies_with_content_fingerprint(tmp_path):
    """Same length + same tail instant, swapped middle image -> recompute."""
    service = _bounds_service(tmp_path)
    calls = _counting_bounds(service)
    snaps_a = [_snap("a1", "a2", 0.0), _snap("b1", "b2", 1.0), _snap("c1", "c2", 2.0)]
    snaps_b = [_snap("a1", "a2", 0.0), _snap("X1", "X2", 1.0), _snap("c1", "c2", 2.0)]
    first = service.get_cached_global_bounds(snaps_a, False)
    assert calls["n"] == 1
    second = service.get_cached_global_bounds(snaps_b, False)
    assert calls["n"] == 2, "stale bounds reused for swapped-middle content"
    assert second is not first
    assert second.pad_bottom == 2


def test_bounds_key_varies_with_auto_crop(tmp_path):
    service = _bounds_service(tmp_path)
    calls = _counting_bounds(service)
    snaps = [_snap("a1", "a2", 0.0), _snap("b1", "b2", 1.0)]
    service.get_cached_global_bounds(snaps, False)
    assert calls["n"] == 1
    service.get_cached_global_bounds(snaps, False)
    assert calls["n"] == 1
    service.get_cached_global_bounds(snaps, True)
    assert calls["n"] == 2, "crop-flag change reused bounds baked under the old flag"


def _prescale_request(auto_crop):
    from engine.cache import TargetSurfaceSpec
    from tabs.image_compare.plugins.video_editor.services.video_export_models import (
        VideoRenderRequest,
    )

    return VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=32, height=24, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=auto_crop,
        fit_content=False,
        global_bounds=None,
    )


def test_prescale_key_varies_with_interp_and_auto_crop():
    """Prescale identity: settings-only changes must recompute.

    Drives ``snapshot_pair_token`` (the exact key ``prepare_canvas_frame``
    compares against ``caches.prescaled``) with identical paths and target
    size: an interpolation switch, an auto-crop toggle, or a crop-service
    change must all vary the key, while identical inputs hit. Key variance
    here is what forces the reload + represcale instead of reusing pixels
    baked under the old setting.
    """
    from tabs.image_compare.services.video_snapshot_rendering.prepare import (
        snapshot_pair_token,
    )

    snap = SimpleNamespace(image1_path="p1", image2_path="p2")
    target = (32, 24)
    base = snapshot_pair_token(snap, _prescale_request(False), target, "BILINEAR", None)
    assert snapshot_pair_token(snap, _prescale_request(False), target, "BILINEAR", None) == base
    assert snapshot_pair_token(snap, _prescale_request(False), target, "LANCZOS", None) != base
    assert snapshot_pair_token(snap, _prescale_request(True), target, "BILINEAR", None) != base
    assert snapshot_pair_token(snap, _prescale_request(False), target, "BILINEAR", object()) != base
    # Paths and target size still participate: different content, different key.
    other_paths = SimpleNamespace(image1_path="q1", image2_path="p2")
    assert snapshot_pair_token(other_paths, _prescale_request(False), target, "BILINEAR", None) != base
    assert snapshot_pair_token(snap, _prescale_request(False), (64, 48), "BILINEAR", None) != base


def test_prepare_uses_snapshot_pair_token():
    """Guard: prepare_canvas_frame compares via snapshot_pair_token."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "video_snapshot_rendering"
        / "prepare.py"
    ).read_text(encoding="utf-8")
    assert "snapshot_pair_token(" in src
    assert "cache_key = snapshot_pair_token(" in src
