"""Export/preview parity across the diff x fit-content x interpolation matrix;
mismatched source pairs prescale directly to one shared target size.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §Render/export parity.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from tabs.image_compare.services.snapshot_render_plan_builder import (
    SnapshotRenderPlanBuilder,
)
from shared.image_processing.prescale import prescale_pair
from shared.rendering import get_effective_export_interpolation_method
from tabs.image_compare.canvas.presentation.plan_builder import CanvasGeometry
from tabs.image_compare.canvas.scene import RenderScene

def _store(*, diff_mode: str, interpolation: str):
    return SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(
                diff_mode=diff_mode,
                channel_view_mode="RGB",
                is_horizontal=False,
                split_position_visual=0.5,
                showing_single_image_mode=0,
            ),
            render_config=SimpleNamespace(
                interpolation_method=interpolation,
                zoom_interpolation_method=interpolation,
            ),
            geometry_state=SimpleNamespace(pixmap_width=4, pixmap_height=3),
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(cached_diff_image=None)
            ),
        ),
        runtime_cache=SimpleNamespace(overlay_clip_rect=None),
        document=SimpleNamespace(image1_path="a.png", image2_path="b.png"),
    )

@pytest.mark.parametrize("diff_mode", ["off", "highlight", "grayscale", "edges", "ssim"])
@pytest.mark.parametrize("fit_content", [False, True])
@pytest.mark.parametrize("interpolation", ["NEAREST", "LANCZOS"])
def test_snapshot_render_plan_export_preview_parity_matrix(
    monkeypatch,
    diff_mode,
    fit_content,
    interpolation,
):
    """QRHI_CANVAS_FEATURES.md: export/video paths must share render-plan parity."""
    import tabs.image_compare.services.snapshot_render_plan_builder as builder_module

    fill_rgba = (9, 8, 7, 255)
    diff_image = Image.new("RGBA", (4, 3), (240, 10, 20, 255))
    captured = {}
    canvas_geometry = (
        CanvasGeometry(
            image_width=4,
            image_height=3,
            canvas_width=8,
            canvas_height=3,
            padding_left=2,
            padding_top=0,
            padding_right=2,
            padding_bottom=0,
            virtual_layout=None,
        )
        if fit_content
        else CanvasGeometry(
            image_width=4,
            image_height=3,
            canvas_width=4,
            canvas_height=3,
            padding_left=0,
            padding_top=0,
            padding_right=0,
            padding_bottom=0,
            virtual_layout=None,
        )
    )

    monkeypatch.setattr(
        builder_module,
        "build_cached_diff_image",
        lambda *_args, **_kwargs: diff_image,
    )
    monkeypatch.setattr(
        builder_module,
        "compute_canvas_plan",
        lambda *_args, **_kwargs: canvas_geometry,
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

    def _build_export_render_scene(store, *_args, **_kwargs):
        mode = str(store.viewport.view_state.diff_mode)
        return RenderScene(
            diff_mode_active=mode != "off",
            diff_mode_int={"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}[mode],
            zoom_interpolation_method=get_effective_export_interpolation_method(store.viewport),
        )

    monkeypatch.setattr(builder_module, "build_export_render_scene", _build_export_render_scene)

    def _capture_build_canvas_plan(_store, image1, image2, **kwargs):
        captured["image1"] = image1
        captured["image2"] = image2
        captured.update(kwargs)
        return SimpleNamespace(
            canvas_w=kwargs["target_size"][0],
            canvas_h=kwargs["target_size"][1],
            image1=image1,
            image2=image2,
            render_scene=kwargs["render_scene"],
            display_cache_key=kwargs["display_cache_key"],
            fill_rgba=kwargs["fill_color"],
            image_is_padded_composite=kwargs.get("image_is_padded_composite", False),
            geometry_letterbox=kwargs.get("geometry_letterbox", False),
        )

    monkeypatch.setattr(builder_module, "build_canvas_plan", _capture_build_canvas_plan)

    store = _store(diff_mode=diff_mode, interpolation=interpolation)
    plan = SnapshotRenderPlanBuilder(store).build_render_plan(
        Image.new("RGBA", (4, 3), (1, 2, 3, 255)),
        Image.new("RGBA", (4, 3), (4, 5, 6, 255)),
        display_cache_key=("display",),
        canvas_fill_rgba=fill_rgba,
        canvas_geometry=canvas_geometry,
        allow_feature_layout_fallback=False,
    )

    assert plan.canvas_w >= canvas_geometry.image_width
    assert plan.canvas_h >= canvas_geometry.image_height
    assert captured["target_size"] == (
        canvas_geometry.canvas_width,
        canvas_geometry.canvas_height,
    )
    assert captured["content_size"] == (
        canvas_geometry.image_width,
        canvas_geometry.image_height,
    )
    assert captured["pad_left"] == canvas_geometry.padding_left
    assert captured["pad_top"] == canvas_geometry.padding_top
    assert plan.fill_rgba == fill_rgba
    assert plan.render_scene.zoom_interpolation_method == "LANCZOS"
    assert plan.image_is_padded_composite is False
    assert plan.geometry_letterbox is True
    if fit_content:
        assert getattr(plan.render_scene, "overlay_clip_rect", None) == (
            canvas_geometry.padding_left,
            canvas_geometry.padding_top,
            canvas_geometry.image_width,
            canvas_geometry.image_height,
        )

    if diff_mode == "off":
        assert plan.render_scene.diff_mode_int == 0
        assert plan.display_cache_key == ("display",)
        # Unpadded sources — fill/pads live in geometry + clear color, not pixels.
        assert captured["image1"].getpixel((0, 0)) == (1, 2, 3, 255)
        assert captured["image1"].size == (
            canvas_geometry.image_width,
            canvas_geometry.image_height,
        )
        return

    assert plan.render_scene.diff_mode_int == 0
    assert plan.display_cache_key[0] == "diff_base"
    assert captured["image1"] is captured["image2"]
    assert store.viewport.session_data.render_cache.cached_diff_image is diff_image
    assert captured["image1"].getpixel((0, 0)) == (240, 10, 20, 255)
    assert captured["image1"].size == (
        canvas_geometry.image_width,
        canvas_geometry.image_height,
    )

def test_prescale_pair_keeps_mismatched_sources_at_one_shared_target_size():
    """QRHI_CANVAS_FEATURES.md: video prescale must not downscale low-res side then upscale it."""
    img1 = Image.new("RGBA", (5760, 4288), (0, 0, 0, 255))
    img2 = Image.new("RGBA", (1440, 1072), (255, 255, 255, 255))

    out1, out2 = prescale_pair(img1, img2, 1451, 1080, "LANCZOS")

    assert out1.size == out2.size
    assert out2.size != (384, 285)
    assert out2.width >= 1400
