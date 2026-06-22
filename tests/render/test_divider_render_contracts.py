"""The divider only paints when two images are uploaded and a valid content
rect exists — never on empty or partial state.

Dogma source: docs/dev/CANVAS_FEATURES.md §GPU/Canvas Rendering Contract.
"""

from __future__ import annotations
from types import SimpleNamespace

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

def test_divider_scene_apply_does_not_write_canvas_runtime_split_line():
    from ui.canvas_features.divider.feature import apply_divider_object

    class CanvasWithoutLegacySplitLineApi:
        def set_split_line_params(self, *args, **kwargs):
            raise AssertionError("divider must render through its feature GL pass")

    context = SimpleNamespace(canvas=CanvasWithoutLegacySplitLineApi())
    scene = SimpleNamespace(find_first=lambda _kind: object())

    apply_divider_object(scene, context)

def test_divider_shader_uses_solid_edge_not_alpha_feather():
    """Divider line must not introduce translucent antialias fringes."""
    from pathlib import Path
    from ui.canvas_features.divider import gl_passes

    source = (Path(gl_passes.__file__).parent / "shaders" / "divider.frag").read_text()
    assert "smoothstep" not in source
    assert "color.a *" not in source
    assert "fragColor = color;" in source


def test_divider_is_discovered_as_qrhi_render_pass():
    from ui.canvas_features.divider.gl_passes import DividerPass
    from ui.canvas_infra.scene.gl_pass_registry import get_canvas_render_passes

    assert any(isinstance(render_pass, DividerPass) for render_pass in get_canvas_render_passes())
