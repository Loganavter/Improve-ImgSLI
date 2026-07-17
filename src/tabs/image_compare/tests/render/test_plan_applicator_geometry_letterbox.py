"""Live overlay_clip must not steal letterbox; export geometry_letterbox may.

Dogma: live uncrop/magnifier sets overlay_clip_rect without owning the
framebuffer letterbox. Export/video snapshot sets geometry_letterbox.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_compare.canvas.presentation.plan_applicator import (
    _apply_plan_letterbox_from_clip,
    _compute_inner_content_rect,
    _refresh_live_content_rect,
)


def _plan(*, clip, geometry_letterbox=False, padded=False, canvas=(100, 50), image_size=(80, 50)):
    return SimpleNamespace(
        canvas_w=canvas[0],
        canvas_h=canvas[1],
        image1=SimpleNamespace(width=image_size[0], height=image_size[1]),
        image_is_padded_composite=padded,
        geometry_letterbox=geometry_letterbox,
        render_scene=SimpleNamespace(
            overlay_clip_rect=clip,
            split_position_visual=0.5,
        ),
    )


def test_live_overlay_clip_does_not_override_letterbox_params():
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _store=object(),
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _canvas_frame_letterbox=None,
            _letterbox_fill_rgba=None,
        ),
        width=lambda: 200,
        height=lambda: 100,
    )
    plan = _plan(clip=(10, 0, 80, 50), geometry_letterbox=False)
    _apply_plan_letterbox_from_clip(canvas, plan)
    assert canvas.runtime_state._letterbox_params[0] == (0.0, 0.0, 1.0, 1.0)
    assert canvas.runtime_state._canvas_frame_letterbox is None


def test_geometry_letterbox_plan_sets_shader_params_from_clip():
    """When widget == canvas, clip fractions map 1:1 into widget UV."""
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _canvas_frame_letterbox=None,
            _letterbox_fill_rgba=None,
        ),
        width=lambda: 100,
        height=lambda: 50,
    )
    plan = _plan(clip=(10, 0, 80, 50), geometry_letterbox=True, canvas=(100, 50))
    _apply_plan_letterbox_from_clip(canvas, plan)
    assert canvas.runtime_state._letterbox_params[0] == (0.1, 0.0, 0.8, 1.0)
    assert canvas.runtime_state._canvas_frame_letterbox == (0.0, 0.0, 1.0, 1.0)


def test_geometry_letterbox_nests_clip_inside_widget_fitted_canvas():
    """Preview pane larger than canvas: fit canvas, then nest image clip."""
    # Widget 200x100, canvas 100x50 → canvas frame fills height, centered x.
    # Clip (10,0,80,50) inside canvas → image at x=20+20, w=160 in widget? 
    # Canvas fit: 100x50 into 200x100 → scale=2, frame=(0,0,200,100)? 
    # 100/50 = 2, 200/100 = 2 → exact fill (0,0,200,100).
    # Image: (10*2, 0, 80*2, 50*2) = (20, 0, 160, 100) → UV (0.1, 0, 0.8, 1).
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _canvas_frame_letterbox=None,
            _letterbox_fill_rgba=None,
        ),
        width=lambda: 200,
        height=lambda: 100,
    )
    plan = _plan(clip=(10, 0, 80, 50), geometry_letterbox=True, canvas=(100, 50))
    _apply_plan_letterbox_from_clip(canvas, plan)
    assert canvas.runtime_state._letterbox_params[0] == (0.1, 0.0, 0.8, 1.0)


def test_geometry_letterbox_nests_when_widget_letterboxes_canvas():
    # Widget 200x200, canvas 100x50 → fit height-limited: scale=2, frame 200x100 at y=50.
    # Clip (0,0,100,50) → image (0, 50, 200, 100) → UV (0, 0.25, 1, 0.5).
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _canvas_frame_letterbox=None,
            _letterbox_fill_rgba=None,
        ),
        width=lambda: 200,
        height=lambda: 200,
    )
    plan = _plan(clip=(0, 0, 100, 50), geometry_letterbox=True, canvas=(100, 50))
    plan.fill_rgba = (9, 8, 7, 255)
    _apply_plan_letterbox_from_clip(canvas, plan)
    ox, oy, sx, sy = canvas.runtime_state._letterbox_params[0]
    assert abs(ox - 0.0) < 1e-6
    assert abs(oy - 0.25) < 1e-6
    assert abs(sx - 1.0) < 1e-6
    assert abs(sy - 0.5) < 1e-6
    assert canvas.runtime_state._canvas_frame_letterbox == (0.0, 0.25, 1.0, 0.5)
    assert canvas.runtime_state._letterbox_fill_rgba == (9.0, 8.0, 7.0, 255.0)


def test_live_with_clip_fits_raw_image_not_padded_canvas():
    state = SimpleNamespace(_store=object(), _content_rect_px=None)
    canvas = SimpleNamespace(
        runtime_state=state,
        width=lambda: 200,
        height=lambda: 100,
    )
    plan = _plan(
        clip=(10, 0, 80, 50),
        geometry_letterbox=False,
        canvas=(100, 50),
        image_size=(80, 50),
    )
    _refresh_live_content_rect(canvas, state, plan)
    # Image 80x50 in 200x100 widget → full height, letterboxed horizontally.
    assert state._content_rect_px is not None
    _, _, dw, dh = state._content_rect_px
    assert dh == 100
    assert dw == 160  # 80/50 * 100


def test_live_with_clip_keeps_inner_equal_outer():
    state = SimpleNamespace(_content_rect_px=(20, 0, 160, 100))
    plan = _plan(clip=(10, 0, 80, 50), geometry_letterbox=False)
    inner, split = _compute_inner_content_rect(state, plan)
    assert inner == (20, 0, 160, 100)
    assert split is None
