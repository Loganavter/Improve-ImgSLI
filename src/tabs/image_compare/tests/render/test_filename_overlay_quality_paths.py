"""Quality-during-drag path for the filename overlay.

Falsification story: with the split-divider drag, the label tracks the
divider so ``rw``/``rh`` change every frame, and the 4x-supersample CPU
raster measured 8-50 ms per label per frame (``filename.prepare.raster``).
Fix: while ``cfg.is_interactive_mode`` is set, rasterize at 1x and upload
straight into the sampled texture (skip the Lanczos pass); the settled frame
re-rasterizes at the full 4x. This test pins that switch and the direct
upload target.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget

import pytest

from ui.canvas_infra.rhi.render_metrics import RenderMetrics
from tabs.image_compare.canvas.render_arch import resolve_canvas_style
from tabs.image_compare.canvas.features.filename_overlay.state.config import (
    FilenameOverlayConfig,
)

_NAME = "1x-HurrDeblur-really-long-filename-for-drag-benchmark.png"


class _FakeSlot:
    def __init__(self) -> None:
        self.active = False
        self.vertices = None
        self.content_key = None
        self.smooth = False
        self.vertex_buffer = object()
        self.needs_downsample = False
        self.direct_upload = False
        self.pending_upload_image = None
        self.texture_size = None
        self.raw_texture_size = None
        self.texture = object()
        self.raw_texture = object()
        self.downsample_target = object()
        self.downsample_pipeline = object()
        self.srb_downsample = object()


class _FakeUpdates:
    def __init__(self) -> None:
        self.uploads: list[tuple[object, object]] = []
        self.buffers: list[tuple] = []

    def updateDynamicBuffer(self, *args) -> None:
        self.buffers.append(args)

    def uploadTexture(self, texture, image) -> None:
        self.uploads.append((texture, image))


class _FakeRhi:
    def __init__(self) -> None:
        self.last: _FakeUpdates | None = None

    def nextResourceUpdateBatch(self) -> _FakeUpdates:
        self.last = _FakeUpdates()
        return self.last

    def clipSpaceCorrMatrix(self):
        return SimpleNamespace(data=lambda: [0.0] * 16)


class _FakeGpu:
    def __init__(self) -> None:
        self.slots = [_FakeSlot(), _FakeSlot()]
        self.pipeline = object()
        self.uniform_buffer = object()
        self.rhi = _FakeRhi()

    def ensure_slot_textures(self, slot, raw_size, final_size) -> None:
        slot.raw_texture_size = raw_size
        slot.texture_size = final_size


class _FakeCommandBuffer:
    def __init__(self) -> None:
        self.resource_updates = []

    def resourceUpdate(self, batch) -> None:
        self.resource_updates.append(batch)


def _make_ctx(*, interactive: bool):
    cfg = FilenameOverlayConfig(
        enabled=True,
        name1=_NAME,
        name2=_NAME,
        split_position=0.5,
        divider_thickness=0,
        is_interactive_mode=interactive,
    )
    content_rect = (100, 50, 1000, 600)
    scene_frame = SimpleNamespace(
        feature_payloads={"filename_overlay": cfg},
        image_rect_px=content_rect,
        split_override=None,
        single_image_preview=0,
    )
    metrics = RenderMetrics(
        canvas_to_view=1.0,
        view_to_screen=1.0,
        output_scale=1.0,
        content_width=float(content_rect[2]),
        content_height=float(content_rect[3]),
        mode="interactive",
    )
    style = resolve_canvas_style(scene_frame, metrics).filename_overlay
    return SimpleNamespace(
        scene_frame=scene_frame,
        render_metrics=metrics,
        zoom_level=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        canvas_width=1200,
        canvas_height=800,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
        width=1200,
        height=800,
        resolved_style=SimpleNamespace(filename_overlay=style),
        images_uploaded=[True, True],
    )


@pytest.fixture()
def pass_and_gpu(monkeypatch):
    import tabs.image_compare.canvas.features.filename_overlay.passes as passes

    captured: dict[str, int] = {}

    def _fake_raster(name, rw, rh, *args, **kwargs):
        ss = int(kwargs.get("supersample", 4))
        captured["supersample"] = ss
        return (
            QImage(max(1, rw * ss), max(1, rh), QImage.Format.Format_RGBA8888),
            QSize(rw, rh),
        )

    monkeypatch.setattr(passes, "rasterize_label", _fake_raster)
    pass_ = passes.FilenameOverlayPass()
    gpu = _FakeGpu()
    pass_._gpu = gpu
    return pass_, gpu, captured


def test_interactive_raster_is_1x_and_direct_upload(pass_and_gpu, qapp):
    pass_, gpu, captured = pass_and_gpu
    widget = QWidget()
    pass_.prepare(widget, _make_ctx(interactive=True), _FakeUpdates())

    assert captured["supersample"] == 1, (
        "interactive drag must rasterize at 1x, not the 4x default"
    )
    slot = gpu.slots[0]
    assert slot.direct_upload is True
    assert slot.needs_downsample is False


def test_settled_raster_is_4x_and_downsampled(pass_and_gpu, qapp):
    pass_, gpu, captured = pass_and_gpu
    widget = QWidget()
    pass_.prepare(widget, _make_ctx(interactive=False), _FakeUpdates())

    assert captured["supersample"] == 4, (
        "the settled frame must re-rasterize at the full 4x"
    )
    slot = gpu.slots[0]
    assert slot.direct_upload is False
    assert slot.needs_downsample is True


def test_direct_upload_targets_sampled_texture(pass_and_gpu, qapp):
    pass_, gpu, _captured = pass_and_gpu
    widget = QWidget()
    pass_.prepare(widget, _make_ctx(interactive=True), _FakeUpdates())

    slot = gpu.slots[0]
    sampled_texture = slot.texture
    command_buffer = _FakeCommandBuffer()
    pass_.record_pre_pass(command_buffer, widget, _make_ctx(interactive=True))

    uploads = [
        (tex, img)
        for batch in command_buffer.resource_updates
        for tex, img in batch.uploads
    ]
    assert any(tex is sampled_texture for tex, _ in uploads), (
        "1x interactive raster must upload into slot.texture (sampled directly), "
        "not slot.raw_texture"
    )
    assert gpu.slots[0].direct_upload is False, "direct flag drained after upload"
