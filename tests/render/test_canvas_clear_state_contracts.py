"""Clearing a slot resets canvas runtime flags and the active display name so
stale state does not stick after the images are cleared.

Dogma source: docs/dev/CANVAS_FEATURES.md §GPU/Canvas Rendering Contract.
"""

from __future__ import annotations
from types import SimpleNamespace

def test_document_active_display_name_does_not_stick_after_slot_clear():
    from core.store_document import DocumentModel, ImageItem

    document = DocumentModel(
        image_list1=[ImageItem(display_name="Left.png")],
        current_index1=0,
    )

    assert document.get_current_display_name(1) == "Left.png"
    assert document.get_active_display_name(1) == "Left.png"

    document.image_list1 = []
    document.current_index1 = -1

    assert document.get_current_display_name(1) == "Left.png"
    assert document.get_active_display_name(1) == ""

def test_gl_canvas_clear_resets_runtime_flags(monkeypatch):
    from ui.widgets.gl_canvas.texture_parts import layers

    runtime_state = SimpleNamespace(
        _background_pixmap=object(),
        _feature_overlay_gpu=SimpleNamespace(
            _pixmap=object(),
            _top_left=object(),
            _centers=[object()],
            _radius=4.0,
            _quads=[object()],
            _use_circle_mask=[True],
            _combined_params=[object()],
            _gpu_active=True,
            _gpu_slots=[1],
            _gpu_widget_geometry_sig=(1, 2),
        ),
        _images_uploaded=[True, True],
        _stored_image_ids=("a", "b"),
        _stored_pil_images=[object(), object()],
        _source_pil_images=[object(), object()],
        _source_image_ids=[1, 2],
        _source_images_ready=True,
        _diff_source_pil_image=object(),
        _diff_source_image_id=9,
        _diff_source_ready=True,
        _source_preload_scheduled=True,
        _shader_letterbox_mode=True,
        _content_rect_px=(1, 2, 3, 4),
        _inner_content_rect_px=(5, 6, 7, 8),
        _inner_split_position=0.5,
        _clip_overlays_to_content_rect=True,
        _content_scissor_depth=2,
        _letterbox_params=[1, 2],
        _feature_overlay_quad_ndc=(0.0, 0.0, 1.0, 1.0),
        _capture_center=object(),
        _capture_radius=12.0,
        _capture_circles=[1],
        _guide_sets=[1],
        _hidden_capture_circles=[1],
        _occluded_capture_arcs=[1],
        _hidden_overlay_circles=[1],
        _drag_overlay_visible=True,
        _drag_overlay_horizontal=True,
        _drag_overlay_texts=("A", "B"),
        _drag_overlay_cache_key="drag",
        _drag_overlay_cached_image=object(),
        _paste_overlay_visible=True,
        _paste_overlay_horizontal=True,
        _paste_overlay_hovered_button="left",
        _pending_texture_uploads=[object()],
    )
    widget = SimpleNamespace(runtime_state=runtime_state, texture_ids=[11, 12], update=lambda: None)

    monkeypatch.setattr(layers, "clear_diff_texture", lambda w: setattr(w, "_diff_cleared", True))
    monkeypatch.setattr(layers, "clear_feature_overlay_gpu", lambda w: setattr(w, "_overlay_cleared", True))
    layers.clear(widget)

    assert runtime_state._images_uploaded == [False, False]
    assert runtime_state._stored_pil_images == [None, None]
    assert runtime_state._source_pil_images == [None, None]
    assert runtime_state._source_image_ids == [0, 0]
    assert runtime_state._source_images_ready is False
    assert runtime_state._diff_source_ready is False
    assert runtime_state._content_rect_px is None
    assert runtime_state._inner_content_rect_px is None
    assert runtime_state._inner_split_position is None
    assert runtime_state._clip_overlays_to_content_rect is False
    assert runtime_state._drag_overlay_visible is False
    assert runtime_state._paste_overlay_visible is False
    assert getattr(widget, "_diff_cleared", False) is True
    assert getattr(widget, "_overlay_cleared", False) is True
