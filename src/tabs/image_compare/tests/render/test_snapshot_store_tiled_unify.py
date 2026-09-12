"""Snapshot store presentation must accept TiledPixelStore sources (quick save)."""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    GlobalCanvasBounds,
)


def _build_snapshot():
    return SimpleNamespace(
        image1_path="/tmp/a.png",
        image2_path="/tmp/b.png",
        name1="A",
        name2="B",
        viewport_state=SimpleNamespace(
            clone=lambda: SimpleNamespace(
                session_data=SimpleNamespace(
                    image_state=SimpleNamespace(),
                ),
                render_config=SimpleNamespace(interpolation_method="BILINEAR"),
                view_state=SimpleNamespace(use_magnifier=False),
                geometry_state=SimpleNamespace(),
                interaction_state=SimpleNamespace(),
            ),
            render_config=SimpleNamespace(interpolation_method="BILINEAR"),
            view_state=SimpleNamespace(use_magnifier=False),
        ),
        settings_state=SimpleNamespace(
            freeze_for_export=lambda: SimpleNamespace(auto_crop_black_borders=False),
        ),
    )


def test_get_unified_images_accepts_tiled_pixel_store():
    from tabs.image_compare.canvas.presentation.plan_builder import _get_unified_images

    img1 = TiledPixelStore.from_pil(Image.new("RGBA", (32, 24), (255, 0, 0, 255)))
    img2 = TiledPixelStore.from_pil(Image.new("RGBA", (40, 20), (0, 255, 0, 255)))

    out1, out2 = _get_unified_images(img1, img2, False, None, resize_method="LANCZOS")

    assert out1 is not None and out2 is not None
    assert out1.size == out2.size == (40, 24)


def test_build_snapshot_store_presentation_with_tiled_fit_content():
    from tabs.image_compare.canvas.presentation.plan_builder import (
        build_snapshot_store_presentation,
    )

    snap = _build_snapshot()
    img1 = TiledPixelStore.from_pil(Image.new("RGBA", (64, 48), (255, 0, 0, 255)))
    img2 = TiledPixelStore.from_pil(Image.new("RGBA", (64, 48), (0, 255, 0, 255)))
    bounds = GlobalCanvasBounds(
        pad_left=8,
        pad_right=8,
        pad_top=4,
        pad_bottom=4,
        base_width=64,
        base_height=48,
    )

    presentation = build_snapshot_store_presentation(
        snap,
        img1,
        img2,
        fit_content=True,
        global_bounds=bounds,
        fill_color=(0, 0, 0, 0),
        normalize_snapshot=False,
    )

    display1 = presentation.images.display_image1
    display2 = presentation.images.display_image2
    assert display1 is not None and display2 is not None
    # Pads stay in virtual layout / plan geometry — display stays unpadded.
    assert display1.size == (64, 48)
    assert display2.size == (64, 48)
    assert isinstance(display1, TiledPixelStore)
    assert isinstance(display2, TiledPixelStore)
