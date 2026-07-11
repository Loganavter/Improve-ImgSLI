"""Tests for magnifier snapshot-store helpers.

In CROP mode the video pipeline calls ``normalize_snapshot_store`` and expects
the capture rect to be clamped inside [0..1].

In UNCROP / fit-content mode ``apply_virtual_canvas_layout_to_snapshot_store``
must NOT mutate *magnifier-model* coordinates: the renderer takes
``content_offset_x/y`` + ``content_w/h`` and handles padding natively, and
mutating the model on top of that produced double-compensation bugs (capture
rect drifted, magnifier positions/sizes wrong, border thickness off).

It DOES need to mutate the store/scene-level ``overlay_clip_rect`` and
``split_position_visual`` fields, mirroring what
``gpu_export_scene.py::apply_virtual_canvas_layout_to_scene`` does for the
GPU-proxy export path — nothing else populates those fields for the
snapshot-store path, so leaving them unset desyncs the divider from the
padded canvas. See the file's docstring for the full reasoning.
"""

from __future__ import annotations

from core.store import Store
from domain.types import Point
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel
from tabs.image_compare.canvas.features.magnifier.state.snapshot_store import (
    apply_virtual_canvas_layout_to_snapshot_store,
    normalize_snapshot_store,
)
from tabs.image_compare.canvas.features.magnifier.state.feature_state import get_magnifier_widget_state

def _make_store_with_model(**model_kwargs) -> tuple[Store, MagnifierModel]:
    store = Store()
    state = get_magnifier_widget_state(store.viewport.view_state)
    model = MagnifierModel(**model_kwargs)
    state.models[model.id] = model
    state.active_id = model.id
    return store, model

def test_normalize_clamps_capture_rect_inside_image_bounds():
    """Crop mode: a capture rect that extends past the edge gets pulled in."""
    store, model = _make_store_with_model(
        position=Point(0.95, 0.5), capture_size_relative=0.2,
    )
    normalize_snapshot_store(store)
    assert 0.1 - 1e-6 <= model.position.x <= 0.9 + 1e-6
    assert abs(model.position.x - 0.9) < 1e-6

def test_normalize_clamps_frozen_position_too():
    store, model = _make_store_with_model(
        position=Point(0.5, 0.5),
        frozen_position=Point(0.02, 0.5),
        capture_size_relative=0.3,
    )
    normalize_snapshot_store(store)
    assert model.frozen_position is not None
    assert abs(model.frozen_position.x - 0.15) < 1e-6

def test_normalize_leaves_already_valid_position_alone():
    store, model = _make_store_with_model(
        position=Point(0.5, 0.5), capture_size_relative=0.1,
    )
    normalize_snapshot_store(store)
    assert abs(model.position.x - 0.5) < 1e-6
    assert abs(model.position.y - 0.5) < 1e-6

def _make_layout(x_min=0.0, x_max=1.25, y_min=0.0, y_max=1.0):
    from shared.rendering.layout_contract import NormalizedBounds, VirtualCanvasLayout
    return VirtualCanvasLayout(
        canvas_bounds=NormalizedBounds(x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max),
        content_bounds=NormalizedBounds(x_min=0.0, x_max=1.0, y_min=0.0, y_max=1.0),
    )

def test_virtual_layout_does_not_mutate_position():
    """Uncrop: model.position must NOT shift (renderer handles padding)."""
    store, model = _make_store_with_model(position=Point(0.5, 0.5))
    original = (model.position.x, model.position.y)
    apply_virtual_canvas_layout_to_snapshot_store(
        store, base_w=800, base_h=600, virtual_layout=_make_layout(),
    )
    assert (model.position.x, model.position.y) == original

def test_virtual_layout_does_not_mutate_sizes():
    """Uncrop: relative size fields must NOT scale (renderer handles padding)."""
    store, model = _make_store_with_model(
        size_relative=0.3, capture_size_relative=0.2, spacing_relative=0.05,
        offset_relative=Point(0.1, 0.2),
    )
    apply_virtual_canvas_layout_to_snapshot_store(
        store, base_w=800, base_h=600, virtual_layout=_make_layout(),
    )
    assert model.size_relative == 0.3
    assert model.capture_size_relative == 0.2
    assert model.spacing_relative == 0.05
    assert model.offset_relative.x == 0.1 and model.offset_relative.y == 0.2

def test_virtual_layout_does_not_mutate_thickness():
    """Uncrop: thickness must NOT scale — renderer uses content short edge."""
    store, model = _make_store_with_model(border_thickness=4, divider_thickness=6)
    apply_virtual_canvas_layout_to_snapshot_store(
        store, base_w=800, base_h=600, virtual_layout=_make_layout(),
    )
    assert model.border_thickness == 4
    assert model.divider_thickness == 6

def test_virtual_layout_publishes_clip_rect_on_runtime_cache():
    """Uncrop: overlay_clip_rect is set so _inner_content_rect_px (divider
    clip/position, capture-area clamping) can be derived downstream."""
    store, _ = _make_store_with_model()
    store.runtime_cache.overlay_clip_rect = None
    apply_virtual_canvas_layout_to_snapshot_store(
        store, base_w=800, base_h=600, virtual_layout=_make_layout(),
    )
    assert store.runtime_cache.overlay_clip_rect == (0, 0, 800, 600)

def test_interpolate_viewport_state_does_not_touch_overlay_clip_rect():
    """ViewportState is slotted; setting .overlay_clip_rect on it raises.

    The keyframe interpolator used to assign ``interpolated.overlay_clip_rect``
    — a typo (the field lives on ``ViewportRuntimeCache``). Verify the
    interpolator works on slotted ViewportState without crashing.
    """
    from core.store_viewport import ViewportState
    from tabs.image_compare.plugins.video_editor.services.keyframing.engine.values import (
        interpolate_viewport_state,
    )

    start = ViewportState()
    end = ViewportState()
    result = interpolate_viewport_state(start, end, 0.5)
    assert result is not None
    assert isinstance(result, ViewportState)
