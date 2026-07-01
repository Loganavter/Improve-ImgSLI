"""Feature GL passes run even without base images / on blank frames; the
paste-overlay feature is discoverable and uses its own shader + preview stack
role.

Dogma source: docs/dev/CANVAS_FEATURES.md §GL passes.
"""

from __future__ import annotations

import os
def _read(rel_path: str) -> str:
    path = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, rel_path)
    with open(path, encoding="utf-8") as f:
        return f.read()

def test_qrhi_render_runs_feature_passes():
    """QRhi renderer drives both should_paint and prepare/record for active
    feature passes — equivalent of the legacy paint_gl behavior, now in
    rhi_renderer."""
    content = _read("src/ui/widgets/canvas/rhi_renderer.py")
    assert "iter_active_render_passes" in content
    assert "render_pass.prepare(widget, ctx, updates)" in content
    assert "render_pass.record(command_buffer, widget, ctx)" in content

def test_paste_overlay_feature_is_discoverable():
    content = _read("src/tabs/image_compare/canvas/features/paste_overlay/widget.py")

    assert 'name="paste_overlay"' in content

def test_paste_overlay_pass_uses_own_shader_and_preview_stack_role():
    content = _read("src/tabs/image_compare/canvas/features/paste_overlay/passes.py")

    assert "class PasteOverlayPass(CanvasRenderPass):" in content
    assert "stack_role = CanvasStackRole.TRANSIENT_PREVIEW" in content
    assert "BlendFactor.OneMinusSrcAlpha" in content
    assert "paste_overlay.vert.qsb" in content
    assert "paste_overlay.frag.qsb" in content


def test_paste_overlay_pass_has_compiled_shaders():
    base = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                        "src/tabs/image_compare/canvas/features/paste_overlay/shaders")
    assert os.path.isfile(os.path.join(base, "paste_overlay.vert.qsb"))
    assert os.path.isfile(os.path.join(base, "paste_overlay.frag.qsb"))


def test_paste_overlay_pass_registered_for_qrhi():
    from tabs.image_compare.tab import ImageCompareTab
    from ui.canvas_infra.scene.gl_pass_registry import get_canvas_render_passes

    ImageCompareTab().register_canvas_features()
    names = {type(p).__name__ for p in get_canvas_render_passes()}
    assert "PasteOverlayPass" in names
