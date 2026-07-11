"""Video preview render sizing: respects device pixel ratio and preview scale,
quality scales large previews, uses the main renderer (not thumbnail), and
prescale targets the exact output size.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §Render/export parity.
"""

from __future__ import annotations
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QObject

def _build_preview_coordinator(*, device_pixel_ratio: float = 1.0):
    from tabs.image_compare.plugins.video_editor.presenter_parts.preview import PreviewCoordinator

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

    assert (render_w, render_h) == (960, 540)

def test_preview_render_size_quality_scales_large_preview():
    coordinator = _build_preview_coordinator(device_pixel_ratio=1.0)
    coordinator.model.width = 1451
    coordinator.model.height = 1080

    coordinator.preview_render_scale = 1.0
    full_w, full_h = coordinator._resolve_preview_render_size(1954, 1066)

    coordinator.preview_render_scale = 0.5
    half_w, half_h = coordinator._resolve_preview_render_size(1954, 1066)

    assert (full_w, full_h) == (1451, 1080)
    assert half_w < full_w
    assert half_h < full_h
    assert (half_w, half_h) == (726, 540)

def test_preview_scene_uses_main_renderer_not_thumbnail(monkeypatch):
    from tabs.image_compare.plugins.video_editor.presenter_parts import preview as preview_module

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

def test_preview_scene_forces_canvas_read_only(monkeypatch):
    from tabs.image_compare.plugins.video_editor.presenter_parts import preview as preview_module

    coordinator = _build_preview_coordinator()
    read_only_calls = []
    monkeypatch.setattr(
        preview_module,
        "apply_canvas_render_plan",
        lambda *args, **kwargs: None,
    )

    class FakeExporter:
        def prepare_snapshot_canvas_frame(self, snap, out_w, out_h, **kwargs):
            return SimpleNamespace(plan=object(), store=object())

    coordinator.export_controller = SimpleNamespace(video_exporter=FakeExporter())
    coordinator.view.preview_label = SimpleNamespace(
        set_read_only=lambda value: read_only_calls.append(value),
    )

    assert coordinator._apply_preview_scene(
        snap=object(),
        request_key=("req",),
        global_bounds=None,
        fill_color_tuple=None,
        render_w=640,
        render_h=360,
    ) is True
    assert read_only_calls == [True]

def test_video_editor_ready_does_not_activate_from_background(monkeypatch):
    from PySide6.QtCore import Qt
    from tabs.image_compare.plugins.video_editor import plugin as plugin_module
    from tabs.image_compare.plugins.video_editor.plugin import VideoEditorPlugin

    calls: list[str] = []
    dialog = SimpleNamespace(
        isMinimized=lambda: False,
        show=lambda: calls.append("show"),
        raise_=lambda: calls.append("raise"),
        activateWindow=lambda: calls.append("activate"),
    )
    app = SimpleNamespace(
        applicationState=lambda: Qt.ApplicationState.ApplicationInactive,
        activeWindow=lambda: None,
        processEvents=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(plugin_module.QApplication, "instance", lambda *_args, **_kwargs: app)

    editor_plugin = VideoEditorPlugin()
    editor_plugin._editor_dialog = dialog
    editor_plugin._show_editor_dialog()

    assert calls == ["show"]

def test_snapshot_frame_renderer_content_fit_uses_requested_resampler(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services import video_snapshot_rendering as rendering

    calls = []

    def fake_resample_image(image, target_size, method_name, is_interactive_render, diff_mode_active=False):
        calls.append(
            {
                "size": target_size,
                "method": method_name,
                "interactive": is_interactive_render,
                "diff": diff_mode_active,
            }
        )
        return image.resize(target_size, Image.Resampling.NEAREST)

    monkeypatch.setattr(rendering, "resample_image", fake_resample_image)

    fitted = rendering.SnapshotFrameRenderer._fit_source_to_content(
        Image.new("RGBA", (8, 8), (255, 255, 255, 255)),
        (4, 4),
        resize_method="LANCZOS",
    )

    assert fitted.size == (4, 4)
    assert calls == [
        {
            "size": (4, 4),
            "method": "LANCZOS",
            "interactive": False,
            "diff": False,
        }
    ]

def test_snapshot_frame_renderer_prescale_target_uses_exact_output_size():
    from tabs.image_compare.plugins.video_editor.services.video_export_models import VideoRenderRequest
    from tabs.image_compare.plugins.video_editor.services.video_snapshot_rendering import SnapshotFrameRenderer
    from shared.rendering import TargetSurfaceSpec

    request = VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=1954, height=1066, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
    )

    assert SnapshotFrameRenderer._resolve_prescale_target(request) == (1954, 1066)

def test_prescale_pair_unifies_mismatched_sources_directly():
    from shared.image_processing.prescale import prescale_pair

    img1 = Image.new("RGBA", (5760, 4288), (0, 0, 0, 255))
    img2 = Image.new("RGBA", (1440, 1072), (255, 255, 255, 255))

    out1, out2 = prescale_pair(img1, img2, 1451, 1080, "LANCZOS")

    assert out1.size == (1450, 1080)
    assert out2.size == (1450, 1080)

def test_snapshot_frame_renderer_prescale_target_keeps_fit_content_base_visible():
    from tabs.image_compare.plugins.video_editor.services.video_export_models import (
        GlobalCanvasBounds,
        VideoRenderRequest,
    )
    from tabs.image_compare.plugins.video_editor.services.video_snapshot_rendering import SnapshotFrameRenderer
    from shared.rendering import TargetSurfaceSpec

    request = VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=594, height=562, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=False,
        fit_content=True,
        global_bounds=GlobalCanvasBounds(
            pad_left=1903,
            pad_right=1903,
            pad_top=0,
            pad_bottom=0,
            base_width=5760,
            base_height=4288,
            canvas_x_min=-0.33045697316157685,
            canvas_x_max=1.3304569731615768,
            canvas_y_min=0.0,
            canvas_y_max=1.0,
        ),
    )

    target_w, target_h = SnapshotFrameRenderer._resolve_prescale_target(request)

    assert target_w >= 594
    assert target_h >= 562

def test_snapshot_frame_renderer_coerces_nearest_export_resampler(monkeypatch):
    from tabs.image_compare.plugins.video_editor.services.video_export_models import VideoRenderRequest
    from tabs.image_compare.plugins.video_editor.services.video_snapshot_rendering import SnapshotFrameRenderer
    from shared.rendering import TargetSurfaceSpec

    class Renderer(SnapshotFrameRenderer):
        def _prepare_canvas_frame_core(self, snap, request, img1, img2, **kwargs):
            return SimpleNamespace(
                store=object(),
                plan=SimpleNamespace(canvas_w=8, canvas_h=8),
                output_width=8,
                output_height=8,
                image_dest_x=0,
                image_dest_y=0,
                fill_rgba=(0, 0, 0, 0),
                debug=kwargs["debug"],
            )

    calls = []

    def fake_prescale_pair(img1, img2, output_width, output_height, method_name):
        calls.append(method_name)
        return img1, img2

    monkeypatch.setattr(
        "tabs.image_compare.plugins.video_editor.services.video_snapshot_rendering.prescale_pair",
        fake_prescale_pair,
    )

    snap = SimpleNamespace(
        image1_path="a",
        image2_path="b",
        viewport_state=SimpleNamespace(
            render_config=SimpleNamespace(interpolation_method="NEAREST")
        ),
    )
    request = VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=8, height=8, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
    )
    renderer = Renderer(
        image_loader=lambda *_args, **_kwargs: Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    )

    renderer.prepare_canvas_frame(snap, request)

    assert calls == ["LANCZOS"]
