"""Export/video diff support: a precomputed/cached diff image is used as the
GPU render-plan base (not a shader diff over padded textures), and export base
filtering coerces ``NEAREST`` to an export-safe resampler.

Dogma source: docs/dev/CANVAS_FEATURES.md §Render/export parity.
"""

import os
from types import SimpleNamespace

from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from plugins.export.services.image_export import ExportService
from plugins.export.services.gpu_export_scene import build_export_gl_scene
from plugins.export.services.snapshot_render_plan_builder import SnapshotRenderPlanBuilder
from ui.canvas_presentation.plan_builder import CanvasGeometry
from ui.widgets.gl_canvas.scene import GLRenderScene
from plugins.video_editor.services.video_export_models import VideoRenderRequest
from plugins.video_editor.services.video_snapshot_rendering import (
    PreparedCanvasFrame,
    SnapshotFrameRenderer,
)
from shared.rendering import TargetSurfaceSpec

class _FakeGpuExportService:
    def __init__(self):
        self.calls = []

    def render_plan(self, plan, *, store=None, diff_image=None):
        self.calls.append(
            {
                "plan": plan,
                "store": store,
                "diff_image": diff_image,
            }
        )
        return Image.new("RGBA", (8, 8), (0, 0, 0, 0)), {}

def test_export_service_passes_cached_diff_image_to_gpu_render_plan(tmp_path):
    gpu = _FakeGpuExportService()
    service = ExportService(font_path_absolute="", gpu_export_service=gpu)

    diff_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    render_store = SimpleNamespace(
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(cached_diff_image=diff_image)
            )
        )
    )
    export_options = {
        "output_dir": str(tmp_path),
        "file_name": "diff-export",
        "format": "PNG",
        "fill_background": False,
        "include_metadata": False,
    }

    out_path = service.export_image(
        store=SimpleNamespace(),
        original_image1=Image.new("RGBA", (8, 8), (0, 0, 0, 255)),
        original_image2=Image.new("RGBA", (8, 8), (255, 255, 255, 255)),
        export_options=export_options,
        render_plan=SimpleNamespace(),
        render_store=render_store,
    )

    assert os.path.isfile(out_path)
    assert gpu.calls[0]["diff_image"] is diff_image

def test_snapshot_frame_renderer_passes_cached_diff_image_to_gpu_preview():
    gpu = _FakeGpuExportService()
    renderer = SnapshotFrameRenderer(image_loader=lambda *_args, **_kwargs: None, gpu_export_service=gpu)

    diff_image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    prepared = PreparedCanvasFrame(
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                session_data=SimpleNamespace(
                    render_cache=SimpleNamespace(cached_diff_image=diff_image)
                )
            )
        ),
        plan=SimpleNamespace(canvas_w=8, canvas_h=8),
        output_width=8,
        output_height=8,
        image_dest_x=0,
        image_dest_y=0,
        fill_rgba=(0, 0, 0, 0),
        debug={},
    )
    request = VideoRenderRequest(
        target_surface=TargetSurfaceSpec(width=8, height=8, fill_rgba=(0, 0, 0, 0)),
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
    )

    result = renderer._render_prepared(prepared, request)

    assert result.image.size == (8, 8)
    assert gpu.calls[0]["diff_image"] is diff_image

def test_snapshot_builder_uses_precomputed_diff_as_export_base(monkeypatch):
    import plugins.export.services.snapshot_render_plan_builder as builder_module

    diff_image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    captured = {}

    monkeypatch.setattr(
        builder_module,
        "build_cached_diff_image",
        lambda *_args, **_kwargs: diff_image,
    )
    monkeypatch.setattr(
        builder_module,
        "compute_canvas_plan",
        lambda *_args, **_kwargs: CanvasGeometry(
            image_width=2,
            image_height=2,
            canvas_width=4,
            canvas_height=2,
            padding_left=1,
            padding_top=0,
            padding_right=1,
            padding_bottom=0,
            virtual_layout=None,
        ),
    )
    monkeypatch.setattr(
        builder_module,
        "compute_export_stroke_scales",
        lambda *_args, **_kwargs: (1.0, 1.0, 1.0),
    )
    monkeypatch.setattr(
        builder_module,
        "query_guides_state",
        lambda _view: SimpleNamespace(
            enabled=False,
            thickness=1,
            color=SimpleNamespace(r=255, g=255, b=255, a=255),
        ),
    )
    monkeypatch.setattr(
        builder_module,
        "build_divider_export_overlay",
        lambda *_args, **_kwargs: {"thickness": 0},
    )
    monkeypatch.setattr(
        builder_module,
        "query_active_magnifier_divider_thickness",
        lambda _store: 0,
    )
    monkeypatch.setattr(
        builder_module,
        "build_export_gl_scene",
        lambda *_args, **_kwargs: GLRenderScene(
            diff_mode_active=True,
            diff_mode_int=1,
            channel_mode_int=2,
        ),
    )

    def _capture_build_canvas_plan(_store, image1, image2, **kwargs):
        captured["image1"] = image1
        captured["image2"] = image2
        captured["gl_scene"] = kwargs["gl_scene"]
        captured["display_cache_key"] = kwargs["display_cache_key"]
        return SimpleNamespace(canvas_w=4, canvas_h=2)

    monkeypatch.setattr(builder_module, "build_canvas_plan", _capture_build_canvas_plan)

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode="highlight", channel_view_mode="R"),
            geometry_state=SimpleNamespace(pixmap_width=2, pixmap_height=2),
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(cached_diff_image=None)
            ),
        )
    )

    plan = SnapshotRenderPlanBuilder(store).build_render_plan(
        Image.new("RGBA", (2, 2), (0, 0, 0, 255)),
        Image.new("RGBA", (2, 2), (255, 255, 255, 255)),
        canvas_fill_rgba=(10, 20, 30, 255),
    )

    assert plan.canvas_w == 4
    assert captured["image1"] is captured["image2"]
    assert captured["image1"].size == (4, 2)
    assert captured["image1"].getpixel((0, 0)) == (10, 20, 30, 255)
    assert captured["image1"].getpixel((1, 0)) == (255, 0, 0, 255)
    assert captured["gl_scene"].diff_mode_active is False
    assert captured["gl_scene"].diff_mode_int == 0
    assert captured["gl_scene"].channel_mode_int == 0
    assert captured["display_cache_key"][0] == "diff_base"
    assert store.viewport.session_data.render_cache.cached_diff_image is diff_image

def test_snapshot_builder_reuses_cached_diff_scene_images(monkeypatch):
    import plugins.export.services.snapshot_render_plan_builder as builder_module

    diff_image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    build_calls = []

    def _build_cached_diff_image(*_args, **_kwargs):
        build_calls.append(1)
        return diff_image

    monkeypatch.setattr(builder_module, "build_cached_diff_image", _build_cached_diff_image)
    monkeypatch.setattr(
        builder_module,
        "compute_canvas_plan",
        lambda *_args, **_kwargs: CanvasGeometry(
            image_width=2,
            image_height=2,
            canvas_width=4,
            canvas_height=2,
            padding_left=1,
            padding_top=0,
            padding_right=1,
            padding_bottom=0,
            virtual_layout=None,
        ),
    )
    monkeypatch.setattr(
        builder_module,
        "compute_export_stroke_scales",
        lambda *_args, **_kwargs: (1.0, 1.0, 1.0),
    )
    monkeypatch.setattr(
        builder_module,
        "query_guides_state",
        lambda _view: SimpleNamespace(
            enabled=False,
            thickness=1,
            color=SimpleNamespace(r=255, g=255, b=255, a=255),
        ),
    )
    monkeypatch.setattr(
        builder_module,
        "build_divider_export_overlay",
        lambda *_args, **_kwargs: {"thickness": 0},
    )
    monkeypatch.setattr(
        builder_module,
        "query_active_magnifier_divider_thickness",
        lambda _store: 0,
    )
    monkeypatch.setattr(
        builder_module,
        "build_export_gl_scene",
        lambda *_args, **_kwargs: GLRenderScene(diff_mode_active=True, diff_mode_int=1),
    )
    monkeypatch.setattr(
        builder_module,
        "build_canvas_plan",
        lambda _store, _image1, _image2, **_kwargs: SimpleNamespace(canvas_w=4, canvas_h=2),
    )

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode="highlight", channel_view_mode="RGB"),
            geometry_state=SimpleNamespace(pixmap_width=2, pixmap_height=2),
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(cached_diff_image=None)
            ),
        )
    )
    builder = SnapshotRenderPlanBuilder(store)
    scene_images_cache = {}
    image1 = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
    image2 = Image.new("RGBA", (2, 2), (255, 255, 255, 255))

    builder.build_render_plan(
        image1,
        image2,
        display_cache_key=("display",),
        canvas_fill_rgba=(0, 0, 0, 0),
        scene_images_cache=scene_images_cache,
    )
    builder.build_render_plan(
        image1,
        image2,
        display_cache_key=("display",),
        canvas_fill_rgba=(0, 0, 0, 0),
        scene_images_cache=scene_images_cache,
    )

    assert len(build_calls) == 1
    assert store.viewport.session_data.render_cache.cached_diff_image is diff_image

def test_export_gl_scene_uses_main_interpolation_for_base_filter(monkeypatch):
    import plugins.export.services.gpu_export_scene as scene_module

    monkeypatch.setattr(
        scene_module,
        "build_gl_render_scene",
        lambda *_args, **_kwargs: GLRenderScene(zoom_interpolation_method="NEAREST"),
    )

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(
                interpolation_method="LANCZOS",
                zoom_interpolation_method="NEAREST",
            )
        )
    )

    scene = build_export_gl_scene(store, divider_thickness_export=0)

    assert scene.zoom_interpolation_method == "LANCZOS"

def test_export_gl_scene_coerces_nearest_for_base_filter(monkeypatch):
    import plugins.export.services.gpu_export_scene as scene_module

    monkeypatch.setattr(
        scene_module,
        "build_gl_render_scene",
        lambda *_args, **_kwargs: GLRenderScene(zoom_interpolation_method="NEAREST"),
    )

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(
                interpolation_method="NEAREST",
                zoom_interpolation_method="NEAREST",
            )
        )
    )

    scene = build_export_gl_scene(store, divider_thickness_export=0)

    assert scene.zoom_interpolation_method == "LANCZOS"
