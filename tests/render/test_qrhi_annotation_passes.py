"""Guides and capture rings are feature-owned QRhi passes."""

from types import SimpleNamespace


def test_guides_require_runtime_geometry():
    from ui.canvas_features.guides.gl_passes import GuidesPass

    empty = SimpleNamespace(
        widget=SimpleNamespace(runtime_state=SimpleNamespace(_guide_sets=[])),
        scene_frame=SimpleNamespace(single_image_preview=0),
        width=100,
        height=100,
    )
    populated = SimpleNamespace(
        widget=SimpleNamespace(runtime_state=SimpleNamespace(_guide_sets=[object()])),
        scene_frame=SimpleNamespace(single_image_preview=0),
        width=100,
        height=100,
    )

    assert GuidesPass().should_paint(empty) is False
    assert GuidesPass().should_paint(populated) is True


def test_guides_and_capture_are_discovered_as_qrhi_passes():
    from ui.canvas_features.capture.gl_passes import CaptureRingPass
    from ui.canvas_features.guides.gl_passes import GuidesPass
    from ui.canvas_infra.scene.gl_pass_registry import get_canvas_render_passes

    passes = get_canvas_render_passes()

    assert any(isinstance(render_pass, GuidesPass) for render_pass in passes)
    assert any(isinstance(render_pass, CaptureRingPass) for render_pass in passes)
