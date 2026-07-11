"""QRhi migration Step 1 keeps the canvas constructible and records a clear pass."""

from types import SimpleNamespace
import struct

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QRhiWidget

from ui.widgets.canvas.rhi_render import render_clear_frame, resolve_clear_color
from tabs.image_compare.canvas.rhi_renderer import pack_base_uniforms
from tabs.image_compare.canvas.texture_parts.upload_queue import queue_texture_upload
from tabs.image_compare.canvas.widget import CanvasWidget


class _Palette:
    def __init__(self, color: QColor):
        self._color = color

    def color(self, _role: QPalette.ColorRole) -> QColor:
        return QColor(self._color)


def test_canvas_widget_uses_qrhi_widget():
    assert issubclass(CanvasWidget, QRhiWidget)
    assert "render" in CanvasWidget.__dict__
    assert "paintGL" not in CanvasWidget.__dict__


def test_resolve_clear_color_prefers_export_plan_fill():
    widget = SimpleNamespace(
        _active_render_plan=SimpleNamespace(fill_rgba=(12, 34, 56, 78)),
        _use_plan_fill_clear=True,
        palette=lambda: _Palette(QColor("black")),
    )

    assert resolve_clear_color(widget).getRgb() == (12, 34, 56, 78)


def test_render_clear_frame_delegates_to_qrhi_renderer():
    calls = []

    class _Renderer:
        def render(self, widget, command_buffer, color):
            calls.append((widget, command_buffer, color.getRgb()))

    widget = SimpleNamespace(
        _active_render_plan=None,
        _use_plan_fill_clear=False,
        _theme_background_color=QColor(1, 2, 3),
        palette=lambda: _Palette(QColor("black")),
        _rhi_renderer=_Renderer(),
    )
    command_buffer = object()

    render_clear_frame(widget, command_buffer)

    assert calls == [(widget, command_buffer, (1, 2, 3, 255))]


def test_base_uniform_block_matches_shader_std140_layout():
    rhi = SimpleNamespace(
        clipSpaceCorrMatrix=lambda: SimpleNamespace(
            data=lambda: (
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )
        )
    )
    base = SimpleNamespace(
        pan_offset_x=0.25,
        pan_offset_y=-0.5,
        zoom=2.0,
        split_position=0.75,
        letterbox1=(0.1, 0.2, 0.3, 0.4),
        letterbox2=(0.5, 0.6, 0.7, 0.8),
        is_horizontal=True,
        channel_mode_int=3,
        diff_mode_int=4,
    )

    block = pack_base_uniforms(
        rhi,
        base,
        diff_source_ready=True,
        tile_rect1=(0.0, 0.25, 0.5, 0.75),
        tile_rect2=(0.1, 0.2, 0.3, 0.4),
    )

    assert len(block) == 192
    assert struct.unpack_from("<4f", block, 64) == (0.25, -0.5, 2.0, 2.0)
    assert struct.unpack_from("<f", block, 80) == (0.75,)
    assert struct.unpack_from("<4i", block, 128) == (1, 3, 4, 1)
    assert struct.unpack_from("<4f", block, 160) == pytest.approx((0.0, 0.25, 0.5, 0.75))
    assert struct.unpack_from("<4f", block, 176) == pytest.approx((0.1, 0.2, 0.3, 0.4))


def test_base_uniform_block_defaults_to_full_tile_rect():
    rhi = SimpleNamespace(
        clipSpaceCorrMatrix=lambda: SimpleNamespace(
            data=lambda: (
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )
        )
    )
    base = SimpleNamespace(
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        zoom=1.0,
        split_position=0.5,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        is_horizontal=False,
        channel_mode_int=0,
        diff_mode_int=0,
    )

    block = pack_base_uniforms(rhi, base, diff_source_ready=False)

    assert len(block) == 192
    assert struct.unpack_from("<4f", block, 160) == (0.0, 0.0, 1.0, 1.0)
    assert struct.unpack_from("<4f", block, 176) == (0.0, 0.0, 1.0, 1.0)


def test_pil_upload_queue_uses_logical_texture_key():
    from PIL import Image

    state = SimpleNamespace(_pending_texture_uploads=[], _images_uploaded=[False, False])
    widget = SimpleNamespace(runtime_state=state)

    queue_texture_upload(widget, Image.new("RGBA", (3, 2), "red"), "stored_0", 0)

    key, image, slot = state._pending_texture_uploads[0]
    assert (key, image.width(), image.height(), slot) == ("stored_0", 3, 2, 0)
    assert state._images_uploaded == [True, False]
