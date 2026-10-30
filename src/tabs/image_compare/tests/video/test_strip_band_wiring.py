"""Strip atlas phase 2 — band host + recording adapter (CPU, offscreen).

The band's GPU half needs a live window (supervisor proof); everything that
decides *what* it draws is CPU and is pinned here:

* the adapter asks the recording for the frame state and the exporter's proxy
  seam for the pixel pair — a strip tile never decodes on the interaction path;
* the block layout / tile size / block->time mapping come from the timeline's
  own ``strip_block_layout`` (rep frames), never from a second formula;
* one window per view change: the same view does not build twice, a new view
  supersedes the older window, and a stale window is refused at render time;
* a build that raises keeps the previous window (fail-open);
* no timer, settle gate or sleep exists in the strip path.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from PySide6.QtWidgets import QScrollArea
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)

from tabs.image_compare.plugins.video_editor.presenter_parts import (
    strip_band as strip_band_module,
)
from tabs.image_compare.plugins.video_editor.presenter_parts.strip_band import (
    StripBandHost,
)
from tabs.image_compare.plugins.video_editor.services import strip_recording
from tabs.image_compare.plugins.video_editor.services.strip_recording import (
    MAX_BLOCKS,
    StripRecordingAdapter,
    proxy_pair_for,
    timeline_strip_layout,
)
from tabs.image_compare.plugins.video_editor.widgets.timeline import (
    VideoTimelineWidget,
)
from tabs.image_compare.services.video_snapshot_rendering.strip_window import (
    LAYER_PX,
    StripWindowCancelled,
    build_window,
    is_current,
    render_window,
)

_FPS = 10
_FRAMES = 121
_VIEWPORT = (900, 260)
#: Proxy size the exporter seam hands back for a strip tile request.
_PROXY = (160, 90)


# ---------------------------------------------------------------------------
# Harness: real timeline widget + real scroll area (the dialog's own shape).
# ---------------------------------------------------------------------------


class _Recording:
    """Duck-typed recording: frame state per timestamp, no pixels of its own."""

    fps = float(_FPS)

    def __init__(self):
        self.evaluated: list[float] = []

    def evaluate_at(self, timestamp: float):
        self.evaluated.append(float(timestamp))
        return SimpleNamespace(timestamp=float(timestamp))


class _Editor:
    def __init__(self, recording):
        self._recording = recording

    def get_fps(self) -> int:
        return _FPS

    def get_current_recording(self):
        return self._recording


class _Exporter:
    """The exporter seam the strip uses: proxy pair only, never a decode."""

    def __init__(self):
        self.calls: list[tuple] = []

    def _resolve_thumbnail_images(self, snap, auto_crop, target_size):
        self.calls.append((snap, bool(auto_crop), tuple(target_size)))
        image1 = Image.new("RGBA", _PROXY, (20, 40, 60, 255))
        image2 = Image.new("RGBA", _PROXY, (200, 180, 160, 255))
        return ((image1, image2), ("session", "session"))


class _Harness:
    def __init__(self, qapp, *, zoom=1.0):
        self.qapp = qapp
        self.snapshots = [
            SimpleNamespace(timestamp=index / _FPS, frame_index=index)
            for index in range(_FRAMES)
        ]
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.widget = VideoTimelineWidget(self.snapshots, store=None)
        self.scroll.setWidget(self.widget)
        self.scroll.resize(*_VIEWPORT)
        self.scroll.show()
        qapp.processEvents()
        self.widget.set_data(
            self.snapshots, fps=_FPS, duration=(_FRAMES - 1) / _FPS
        )
        self.widget.resize(880, 220)
        self.widget.fit_view()
        if zoom is not None:
            self.widget.set_zoom(float(zoom))
        self.widget.update_layout_width()
        qapp.processEvents()
        self.recording = _Recording()
        self.editor = _Editor(self.recording)
        self.exporter = _Exporter()

    def view(self):
        return SimpleNamespace(timeline=self.widget)

    def host(self, **kwargs):
        return StripBandHost(
            view=self.view(),
            editor_service=self.editor,
            export_controller=SimpleNamespace(video_exporter=self.exporter),
            **kwargs,
        )

    def scroll_to(self, value: int) -> None:
        self.scroll.horizontalScrollBar().setValue(int(value))
        self.qapp.processEvents()

    def close(self) -> None:
        self.widget.close()
        self.scroll.close()
        self.scroll.deleteLater()


def _plain_plan_builder(snapshot, request, image1, image2):
    """Stand-in for the production plan builder: a plan carrying the proxies."""
    scene = SimpleNamespace(
        split_position_visual=0.5,
        is_horizontal=False,
        overlay_clip_rect=None,
        feature_overrides={},
        channel_mode_int=0,
        diff_mode_int=0,
    )
    plan = SimpleNamespace(
        render_scene=scene,
        image1=image1,
        image2=image2,
        canvas_w=image1.width,
        canvas_h=image1.height,
        fill_rgba=(0, 0, 0, 0),
        geometry_letterbox=False,
        image_is_padded_composite=False,
    )
    return SimpleNamespace(plan=plan)


def _recording_builder(*args, **kwargs):
    """The real ``build_window`` with the fake plan builder injected."""
    kwargs["plan_builder"] = _plain_plan_builder
    return build_window(*args, **kwargs)


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


def _layout(harness):
    current = timeline_strip_layout(harness.widget, fps=_FPS)
    assert current is not None, "the fitted strip must lay out at least one block"
    return current


def test_layout_is_the_timeline_block_layout(qapp):
    """Tile size, block count and block->time all come from the timeline."""
    harness = _Harness(qapp)
    try:
        layout, first_block, count = _layout(harness)

        assert count >= 2
        expected_w = min(
            int(round(timeline_viewport.get_base_tile_width(harness.widget))),
            LAYER_PX,
        )
        expected_h = min(int(harness.widget.STRIP_HEIGHT), LAYER_PX)
        assert layout.tile_size == (expected_w, expected_h)
        assert layout.fps == _FPS
        # One row: tile i lands on block i of the strip.
        assert layout.cols == count
        assert layout.first_block == first_block
        assert layout.block_count == count

        span = timeline_viewport._strip_visible_span(harness.widget)
        blocks = timeline_viewport.strip_block_layout(
            harness.widget,
            content_start_x=span[0],
            start_x=span[1],
            end_x=span[2],
            overscan_blocks=0,
        )
        # The block's TIME is its representative frame over fps — never
        # block/fps (a block spans several frames at the fitted zoom).
        assert [
            layout.block_time(first_block + index) for index in range(count)
        ] == [block[2] / _FPS for block in blocks[:count]]
        first, last = timeline_viewport.visible_strip_block_range(
            harness.widget, overscan_blocks=0
        )
        assert (first_block, first_block + count) == (
            first,
            min(last, first + MAX_BLOCKS),
        )
    finally:
        harness.close()


def test_scrolling_moves_the_window_to_later_blocks(qapp):
    harness = _Harness(qapp)
    try:
        _, first_before, _ = _layout(harness)
        harness.scroll_to(400)
        _, first_after, _ = _layout(harness)
        assert first_after > first_before
    finally:
        harness.close()


def test_block_time_is_the_block_representative_frame(qapp):
    """At the fitted zoom one block spans several frames — not ``block / fps``.

    The discriminating view: ``block / fps`` would agree with the truth when a
    block IS a frame (zoom 1), so the assertion runs where frames_per_block > 1
    (the fitted strip the editor opens on).
    """
    harness = _Harness(qapp, zoom=None)
    try:
        layout, first_block, count = _layout(harness)
        span = timeline_viewport._strip_visible_span(harness.widget)
        blocks = timeline_viewport.strip_block_layout(
            harness.widget,
            content_start_x=span[0],
            start_x=span[1],
            end_x=span[2],
            overscan_blocks=0,
        )
        slot_width = timeline_viewport.get_slot_width(harness.widget)
        frames_per_block = blocks[0][1] / slot_width
        assert frames_per_block > 1.5, "fitted zoom must span frames per block"
        assert count >= 2

        times = [layout.block_time(first_block + index) for index in range(count)]

        assert times == [block[2] / _FPS for block in blocks[:count]]
        assert times[1] != pytest.approx((first_block + 1) / _FPS)
    finally:
        harness.close()


def test_adapter_delegates_the_frame_state_to_the_recording(qapp):
    harness = _Harness(qapp)
    try:
        layout, _first, _count = _layout(harness)
        adapter = StripRecordingAdapter(
            harness.recording,
            proxy_pair=proxy_pair_for(harness.exporter),
            layout=layout,
            fps=layout.fps,
        )

        state = adapter.evaluate_at(0.3)

        assert state.timestamp == pytest.approx(0.3)
        assert harness.recording.evaluated == [pytest.approx(0.3)]
        assert adapter.fps == _FPS
        assert adapter.block_count == layout.block_count
        assert adapter.layout is layout
    finally:
        harness.close()


def test_adapter_returns_the_session_proxy_pair_without_decoding(
    qapp, monkeypatch
):
    """The tile's pixels come from the exporter seam — no decode anywhere."""
    harness = _Harness(qapp)

    def _boom(*_args, **_kwargs):
        raise AssertionError("the strip decoded pixels on the interaction path")

    monkeypatch.setattr(Image, "open", _boom)
    try:
        layout, _first, _count = _layout(harness)
        adapter = StripRecordingAdapter(
            harness.recording,
            proxy_pair=proxy_pair_for(harness.exporter),
            layout=layout,
            fps=layout.fps,
        )
        snapshot = adapter.evaluate_at(0.2)

        pair = adapter.images_for(snapshot, layout.tile_size)

        assert pair is not None
        assert harness.exporter.calls == [
            (snapshot, False, (layout.tile_size[0], layout.tile_size[1]))
        ]
        image1, image2 = pair
        assert (image1.width, image1.height) == _PROXY
        # A miss (no proxy at this size) is a placeholder tile, not a decode.
        harness.exporter.calls.clear()
        assert proxy_pair_for(SimpleNamespace()) is None
        assert proxy_pair_for(harness.exporter)(snapshot, (1, 1))[0] is not None
    finally:
        harness.close()


def test_production_proxy_seam_is_reused_and_never_decodes(monkeypatch):
    """The strip asks the exporter's own seam; a miss is a placeholder."""
    from types import MethodType

    from tabs.image_compare.plugins.video_editor.services.video_export import (
        service as export_service,
    )

    def _boom(*_args, **_kwargs):
        raise AssertionError("fell through to a full-res decode")

    monkeypatch.setattr(export_service, "resolve_thumbnail_proxy_source", _boom)
    proxies = {
        "/missing/a.png": Image.new("RGBA", _PROXY, (10, 20, 30, 255)),
        "/missing/b.png": Image.new("RGBA", _PROXY, (40, 50, 60, 255)),
    }
    stub = SimpleNamespace(
        _thumbnail_proxy_resolver=(
            lambda path, auto_crop, size: (proxies.get(path), "session")
        ),
        _image_repository=None,
        _last_thumbnail_source=None,
    )
    stub._resolve_thumbnail_images = MethodType(
        export_service.VideoExporterService._resolve_thumbnail_images, stub
    )
    snapshot = SimpleNamespace(
        image1_path="/missing/a.png", image2_path="/missing/b.png"
    )

    pair = proxy_pair_for(stub)(snapshot, _PROXY)

    assert pair[0] is proxies["/missing/a.png"]
    assert pair[1] is proxies["/missing/b.png"]
    assert stub._last_thumbnail_source == ("session", "session")


# ---------------------------------------------------------------------------
# The band host
# ---------------------------------------------------------------------------


class _BandStub:
    """Records the callbacks the band would invoke from its GPU frame."""

    def __init__(self):
        self.render = None
        self.release = None
        self.placed: list = []

    def place(self, rect):
        self.placed.append(rect)


def _collecting_builder(calls, window=None):
    def _builder(recording, first_block, count, tile_w, tile_h, **kwargs):
        calls.append((first_block, count, tile_w, tile_h))
        return window if window is not None else SimpleNamespace(
            first_block=first_block, count=count
        )

    return _builder


def test_attach_enables_the_band_and_builds_one_window(qapp):
    harness = _Harness(qapp)
    calls: list = []
    host = harness.host(builder=_collecting_builder(calls))
    try:
        assert host.attach() is True

        band = harness.widget.strip_band()
        assert band is not None
        assert band.renderer() is not None
        assert len(calls) == 1, "attach must plan the current view exactly once"
        assert host.build_count == 1
        # The band sits on the timeline's own strip row, not the whole widget.
        assert band.band_rect() == harness.widget.strip_band_rect()
    finally:
        host.detach()
        harness.close()


def test_one_window_build_per_view_change(qapp):
    harness = _Harness(qapp)
    calls: list = []
    host = harness.host(builder=_collecting_builder(calls))
    try:
        host.attach()
        assert len(calls) == 1

        # Same view: no rebuild, whatever signals fire.
        host.on_view_changed()
        harness.widget.viewportChanged.emit()
        assert len(calls) == 1

        # A real scroll step: one build, from the production signal chain.
        harness.scroll_to(500)
        harness.widget._on_host_scroll()
        assert len(calls) == 2

        # ... and no movement again: still one per change.
        harness.widget._on_host_scroll()
        assert len(calls) == 2
    finally:
        host.detach()
        harness.close()


def test_new_view_supersedes_the_previous_window(qapp):
    harness = _Harness(qapp)
    host = harness.host(builder=_recording_builder)
    try:
        host.attach()
        first = host.window()
        assert first is not None
        assert is_current(first)

        harness.scroll_to(500)
        harness.widget._on_host_scroll()
        second = host.window()

        assert second is not None and second is not first
        assert is_current(second)
        assert first.cancelled, "a newer window must supersede the older one"
        with pytest.raises(StripWindowCancelled):
            # The stale window is refused before any GPU work happens.
            render_window(None, first, rhi=None, command_buffer=None)
    finally:
        host.detach()
        harness.close()


def test_build_failure_keeps_the_previous_window(qapp):
    harness = _Harness(qapp)
    state = {"fail": False}
    calls: list = []

    def _builder(recording, first_block, count, tile_w, tile_h, **kwargs):
        calls.append((first_block, count))
        if state["fail"]:
            raise RuntimeError("no plan builder in this shape")
        return _recording_builder(
            recording, first_block, count, tile_w, tile_h, **kwargs
        )

    host = harness.host(builder=_builder)
    try:
        host.attach()
        window = host.window()
        assert window is not None

        state["fail"] = True
        harness.scroll_to(500)
        harness.widget._on_host_scroll()

        assert len(calls) == 2
        assert host.window() is window, "fail-open: the previous window stays"
        assert host.build_errors == 1
        assert "no plan builder" in (host.last_error or "")
    finally:
        host.detach()
        harness.close()


def test_render_draws_the_built_window_through_the_band(qapp, monkeypatch):
    """The band's render callback hands its own target/RHI to the renderer."""
    harness = _Harness(qapp)
    host = harness.host(builder=_recording_builder)
    drawn: list = []

    def _fake_render(target, window, *, rhi, command_buffer=None, **_kwargs):
        drawn.append((target, window, rhi, command_buffer))

    monkeypatch.setattr(strip_band_module, "render_window", _fake_render)
    try:
        host.attach()
        band = harness.widget.strip_band()
        window = host.window()
        assert window is not None

        sentinel_target = object()
        sentinel_rhi = object()
        monkeypatch.setattr(band, "renderTarget", lambda: sentinel_target)
        monkeypatch.setattr(band, "rhi", lambda: sentinel_rhi)

        host._render("cb", band)

        assert drawn == [(sentinel_target, window, sentinel_rhi, "cb")]
        assert host.render_count == 1
    finally:
        host.detach()
        harness.close()


def test_no_timer_settle_or_sleep_in_the_strip_path():
    """No debounce, no settle gate, no waiting: the strip builds per tick."""
    modules = [
        inspect.getmodule(strip_band_module),
        inspect.getmodule(strip_recording),
    ]
    forbidden = (
        "QTimer",
        "SettleGate",
        "singleShot",
        "time.sleep(",
        "QThread",
        "threading.",
    )
    for module in modules:
        source = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{module.__name__} uses {token}"
