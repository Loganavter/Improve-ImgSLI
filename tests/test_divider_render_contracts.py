from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

def _build_ctx(*, show_divider: bool, thickness: int, images_uploaded, content_rect):
    return SimpleNamespace(
        widget=SimpleNamespace(width=lambda: 100, height=lambda: 100, runtime_state=None),
        images_uploaded=list(images_uploaded),
        scene_frame=SimpleNamespace(
            feature_payloads={
                "show_divider": show_divider,
                "divider_thickness": thickness,
            },
            is_horizontal=False,
            content_rect_px=content_rect,
        ),
    )

def test_divider_does_not_paint_without_uploaded_images():
    from ui.canvas_features.divider.gl_passes import DividerPass

    ctx = _build_ctx(
        show_divider=True,
        thickness=2,
        images_uploaded=[False, False],
        content_rect=(0, 0, 100, 100),
    )

    assert DividerPass().should_paint(ctx) is False

def test_divider_does_not_paint_without_valid_content_rect():
    from ui.canvas_features.divider.gl_passes import DividerPass

    ctx = _build_ctx(
        show_divider=True,
        thickness=2,
        images_uploaded=[True, True],
        content_rect=None,
    )

    assert DividerPass().should_paint(ctx) is False

def test_divider_paints_only_with_two_images_and_content_rect():
    from ui.canvas_features.divider.gl_passes import DividerPass

    ctx = _build_ctx(
        show_divider=True,
        thickness=2,
        images_uploaded=[True, True],
        content_rect=(0, 0, 100, 100),
    )

    assert DividerPass().should_paint(ctx) is True
