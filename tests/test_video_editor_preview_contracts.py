from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from PyQt6.QtCore import QObject

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

def _build_preview_coordinator(*, device_pixel_ratio: float = 1.0):
    from plugins.video_editor.presenter_parts.preview import PreviewCoordinator

    view = SimpleNamespace(
        preview_label=SimpleNamespace(devicePixelRatioF=lambda: device_pixel_ratio),
        get_preview_size=lambda: (640, 360),
    )
    coordinator = PreviewCoordinator(
        view=view,
        export_controller=None,
        playback_engine=SimpleNamespace(),
        model=SimpleNamespace(width=1920, height=1080),
        editor_service=SimpleNamespace(),
        timer_parent=QObject(),
        emit_preview_ready=lambda: None,
    )
    return coordinator

def test_preview_render_size_uses_device_pixel_ratio():
    coordinator = _build_preview_coordinator(device_pixel_ratio=2.0)

    render_w, render_h = coordinator._resolve_preview_render_size(640, 360)

    assert (render_w, render_h) == (1920, 1080)

def test_preview_render_size_respects_preview_scale():
    coordinator = _build_preview_coordinator(device_pixel_ratio=2.0)
    coordinator.preview_render_scale = 0.5

    render_w, render_h = coordinator._resolve_preview_render_size(640, 360)

    assert (render_w, render_h) == (1280, 720)

def test_preview_scene_uses_main_renderer_not_thumbnail(monkeypatch):
    from plugins.video_editor.presenter_parts import preview as preview_module

    coordinator = _build_preview_coordinator()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        preview_module,
        "apply_canvas_render_plan",
        lambda *args, **kwargs: captured.setdefault("applied", True),
    )

    class FakeExporter:
        def prepare_snapshot_canvas_frame(self, snap, out_w, out_h, **kwargs):
            captured["snap"] = snap
            captured["out_w"] = out_w
            captured["out_h"] = out_h
            captured["thumbnail"] = kwargs.get("thumbnail")
            return SimpleNamespace(plan=object(), store=object())

    coordinator.export_controller = SimpleNamespace(video_exporter=FakeExporter())
    coordinator.view.preview_label = SimpleNamespace()

    applied = coordinator._apply_preview_scene(
        snap=object(),
        request_key=("req",),
        global_bounds=None,
        fill_color_tuple=None,
        render_w=640,
        render_h=360,
    )

    assert applied is True
    assert captured["applied"] is True
    assert captured["thumbnail"] is False
