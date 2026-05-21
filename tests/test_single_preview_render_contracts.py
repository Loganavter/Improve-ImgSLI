from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

def test_single_image_preview_helper_reads_scene_frame():
    from ui.canvas_infra.scene.gl_pass_contract import is_single_image_preview_scene

    assert is_single_image_preview_scene(SimpleNamespace(scene_frame=SimpleNamespace(single_image_preview=1))) is True
    assert is_single_image_preview_scene(SimpleNamespace(scene_frame=SimpleNamespace(single_image_preview=0))) is False

def test_divider_does_not_paint_in_single_preview():
    from ui.canvas_features.divider.gl_passes import DividerPass

    ctx = SimpleNamespace(
        widget=SimpleNamespace(width=lambda: 100, height=lambda: 100, runtime_state=None),
        images_uploaded=[True, True],
        scene_frame=SimpleNamespace(
            single_image_preview=1,
            feature_payloads={"show_divider": True, "divider_thickness": 2},
            is_horizontal=False,
            content_rect_px=(0, 0, 100, 100),
        ),
    )

    assert DividerPass().should_paint(ctx) is False

def test_capture_ring_does_not_paint_in_single_preview():
    from ui.canvas_features.capture.gl_passes import CaptureRingPass

    ctx = SimpleNamespace(
        widget=SimpleNamespace(runtime_state=SimpleNamespace(_capture_circles=[(object(), 10.0, object())])),
        scene_frame=SimpleNamespace(single_image_preview=2, feature_payloads={}),
    )

    assert CaptureRingPass().should_paint(ctx) is False
