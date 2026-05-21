from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

def _read(rel_path: str) -> str:
    path = os.path.join(os.path.dirname(__file__), os.pardir, rel_path)
    with open(path, encoding="utf-8") as f:
        return f.read()

def test_paint_gl_runs_feature_passes_without_base_images():
    content = _read("src/ui/widgets/gl_canvas/render_passes.py")

    assert "if not any(ctx.images_uploaded):" in content
    assert 'execute_render_passes(widget, ctx, getattr(widget, "_feature_gl_passes", ()))' in content

def test_paint_gl_runs_feature_passes_on_blank_white_frames():
    content = _read("src/ui/widgets/gl_canvas/render_passes.py")

    assert "if should_render_blank_white(ctx.scene_frame):" in content
    assert "        clear_with_widget_background(widget)\n        execute_render_passes(widget, ctx, getattr(widget, \"_feature_gl_passes\", ()))\n        return" in content

def test_paste_overlay_feature_is_discoverable():
    content = _read("src/ui/canvas_features/paste_overlay/widget.py")

    assert 'name="paste_overlay"' in content

def test_paste_overlay_pass_uses_own_shader_and_preview_stack_role():
    content = _read("src/ui/canvas_features/paste_overlay/gl_passes.py")

    assert "class PasteOverlayPass(CanvasGLRenderPass):" in content
    assert "stack_role = CanvasStackRole.TRANSIENT_PREVIEW" in content
    assert "uniform sampler2D uTex;" in content
    assert 'gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)' in content
