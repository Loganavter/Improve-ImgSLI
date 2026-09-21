"""P2 canvas parity: set_pixmap resets the inner content rect.

Clip readers (``render_config.get_content_rect_screen_px``,
``get_view_transformed_content_rect_widget_px``) prefer
``_inner_content_rect_px`` over ``_content_rect_px``. ``set_pixmap``
refreshed the outer rect for the new single pixmap but left the previous
pair's inner rect/split behind, so live overlays kept clipping to a stale
box while export recomputed from ``overlay_clip_rect`` — a live/export
clip mismatch. Must match ``clear()``: both go back to ``None``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tabs.image_compare.canvas.texture_parts import layers as layers_mod


def _widget():
    state = SimpleNamespace(
        _feature_overlay_gpu=SimpleNamespace(_centers=[], _radius=0),
        _store=object(),
        _background_pixmap=None,
        _stored_pil_images=[None, None],
        _stored_image_ids=None,
        _source_pil_images=[None, None],
        _source_image_ids=[0, 0],
        _source_images_ready=True,
        _capture_center=None,
        _capture_radius=0,
        _content_rect_px=(0, 0, 800, 600),
        _inner_content_rect_px=(100, 50, 600, 500),
        _inner_split_position=0.42,
        _clip_overlays_to_content_rect=True,
    )
    return SimpleNamespace(runtime_state=state, update=lambda: None)


def _pixmap(w=400, h=300):
    pixmap = MagicMock()
    pixmap.width.return_value = w
    pixmap.height.return_value = h
    pixmap.toImage.return_value = MagicMock()
    return pixmap


def test_set_pixmap_clears_stale_inner_rect_and_split(monkeypatch):
    monkeypatch.setattr(layers_mod, "upload_image", lambda *a, **k: None)
    monkeypatch.setattr(layers_mod, "clear_feature_overlay_gpu", lambda *a, **k: None)
    widget = _widget()
    layers_mod.set_pixmap(widget, _pixmap())
    state = widget.runtime_state
    assert state._content_rect_px == (0, 0, 400, 300)
    assert state._inner_content_rect_px is None
    assert state._inner_split_position is None


def test_set_pixmap_none_still_clears_layers(monkeypatch):
    monkeypatch.setattr(layers_mod, "upload_image", lambda *a, **k: None)
    monkeypatch.setattr(layers_mod, "clear_feature_overlay_gpu", lambda *a, **k: None)
    cleared = []
    monkeypatch.setattr(
        layers_mod, "set_layers", lambda *a, **k: cleared.append(True)
    )
    widget = _widget()
    layers_mod.set_pixmap(widget, None)
    assert cleared == [True]
