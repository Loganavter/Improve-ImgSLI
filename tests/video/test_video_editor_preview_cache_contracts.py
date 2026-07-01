"""Snapshot presentation ``display_cache_key`` is stable for identical inputs,
so the preview cache hits instead of re-rendering.

Dogma source: docs/dev/CANVAS_FEATURES.md §Render/export parity.
"""

from __future__ import annotations
from types import SimpleNamespace

from PIL import Image

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

def test_snapshot_presentation_display_cache_key_is_stable_for_same_inputs():
    from tabs.image_compare.canvas.presentation.plan_builder import build_snapshot_store_presentation

    snap = _build_snapshot()
    img1 = Image.new("RGBA", (640, 360), (255, 0, 0, 255))
    img2 = Image.new("RGBA", (640, 360), (0, 255, 0, 255))

    p1 = build_snapshot_store_presentation(
        snap,
        img1,
        img2,
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
    )
    p2 = build_snapshot_store_presentation(
        snap,
        img1.copy(),
        img2.copy(),
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
    )

    assert p1.images.display_cache_key == p2.images.display_cache_key
