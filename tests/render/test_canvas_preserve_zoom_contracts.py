"""Canvas preserve-zoom keeps image focus stable across letterbox changes.

Dogma source: docs/dev/CANVAS_FEATURES.md §Working with zoom & pan.
"""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from ui.canvas_infra.viewport.state import (
    set_pan_offsets,
    set_zoom_level,
)
from ui.canvas_infra.viewport.focus import (
    capture_letterbox_focus,
    restore_letterbox_focus,
)

def _canvas(letterbox):
    return SimpleNamespace(
        runtime_state=SimpleNamespace(_letterbox_params=[letterbox]),
        zoom_level=None,
        pan_offset_x=None,
        pan_offset_y=None,
    )

def test_preserve_zoom_restores_image_focus_after_letterbox_change():
    canvas = _canvas((0.10, 0.00, 0.80, 1.00))
    set_zoom_level(canvas, 8.0)
    set_pan_offsets(canvas, 0.12, -0.04)

    focus = capture_letterbox_focus(canvas)
    canvas.runtime_state._letterbox_params[0] = (0.08, 0.02, 0.84, 0.96)
    assert restore_letterbox_focus(canvas, focus) is True

    assert capture_letterbox_focus(canvas) == focus

def test_preserve_zoom_clamps_pan_to_zero_when_zoom_fits():
    canvas = _canvas((0.10, 0.00, 0.80, 1.00))
    set_zoom_level(canvas, 1.0)
    set_pan_offsets(canvas, 0.12, -0.04)

    focus = capture_letterbox_focus(canvas)
    canvas.runtime_state._letterbox_params[0] = (0.08, 0.02, 0.84, 0.96)
    assert restore_letterbox_focus(canvas, focus) is True

    assert canvas.pan_offset_x == 0.0
    assert canvas.pan_offset_y == 0.0

def test_resize_gl_preserves_image_focus_when_letterbox_changes(monkeypatch):
    """Canvas resize must not preserve raw pan across letterbox changes."""
    import tabs.image_compare.canvas.render_context as render_context

    canvas = _canvas((0.10, 0.00, 0.80, 1.00))
    canvas.runtime_state._shader_letterbox_mode = True
    canvas.runtime_state._stored_pil_images = [object(), None]
    canvas._update_paste_overlay_rects = lambda: None
    canvas.update = lambda: None
    set_zoom_level(canvas, 12.0)
    set_pan_offsets(canvas, 0.12, -0.04)

    focus = capture_letterbox_focus(canvas)
    monkeypatch.setattr(render_context, "has_canvas_feature_live_runtime_overlays", lambda: False)
    monkeypatch.setattr(
        render_context,
        "update_common_letterbox_geometry",
        lambda widget, img1, img2: widget.runtime_state._letterbox_params.__setitem__(
            0,
            (0.08, 0.02, 0.84, 0.96),
        ),
    )

    render_context.resize_gl(canvas, 1200, 900)

    assert capture_letterbox_focus(canvas) == focus

def test_resize_gl_recomputes_aspect_ratio_and_shared_interaction_rect(monkeypatch):
    """Window aspect changes must update both rendering and hit-test geometry."""
    import tabs.image_compare.canvas.render_context as render_context

    dimensions = {"width": 500, "height": 1000}
    image1 = Image.new("RGBA", (1000, 500), "red")
    image2 = Image.new("RGBA", (1000, 500), "blue")
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _shader_letterbox_mode=True,
            _stored_pil_images=[image1, image2],
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _content_rect_px=(0, 0, 1000, 500),
            _clip_overlays_to_content_rect=False,
        ),
        width=lambda: dimensions["width"],
        height=lambda: dimensions["height"],
        _update_paste_overlay_rects=lambda: None,
        update=lambda: None,
    )
    monkeypatch.setattr(
        render_context,
        "has_canvas_feature_live_runtime_overlays",
        lambda: False,
    )

    render_context.resize_gl(canvas, 500, 1000)

    expected = (0.0, 0.375, 1.0, 0.25)
    assert canvas.runtime_state._letterbox_params == [expected, expected]
    assert canvas.runtime_state._content_rect_px == (0, 375, 500, 250)
