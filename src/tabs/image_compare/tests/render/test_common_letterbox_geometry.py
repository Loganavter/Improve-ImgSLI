"""Both comparison textures share one letterbox transform."""

from types import SimpleNamespace

import numpy as np
from PIL import Image

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.canvas.texture_parts.base_images import (
    letterbox_pil,
    update_common_letterbox_geometry,
)


def test_common_letterbox_uses_one_reference_rect_for_both_sides():
    state = SimpleNamespace(
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _clip_overlays_to_content_rect=True,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        width=lambda: 1000,
        height=lambda: 500,
    )

    update_common_letterbox_geometry(
        widget,
        Image.new("RGBA", (2000, 1000)),
        Image.new("RGBA", (1000, 2000)),
    )

    # Eager max envelope: pw,ph = 2000,2000 -> square fitted into 1000x500
    # => 500x500 centered at (250,0)
    assert state._letterbox_params[0] == state._letterbox_params[1]
    assert state._letterbox_params[0] == (0.25, 0.0, 0.5, 1.0)
    assert state._content_rect_px == (250, 0, 500, 500)


def _letterbox_widget(width=800, height=600):
    state = SimpleNamespace(
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
    )
    return SimpleNamespace(
        runtime_state=state,
        width=lambda: width,
        height=lambda: height,
    )


def test_letterbox_pil_from_store_no_full_frame_materialization():
    """letterbox_pil must accept a TiledPixelStore in the "stored" role and
    produce the letterboxed RGBA canvas without materializing the store
    (pyvips-streaming Phase 3, archived plan in the private improve-imgsli-internal-docs repo: the old code called to_pil() here, a
    multi-GB full-frame copy on a 20k source)."""
    arr = np.zeros((400, 600, 4), dtype=np.uint8)
    arr[:, :, :3] = (120, 40, 200)
    arr[:, :, 3] = 255
    store = TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))
    try:
        widget = _letterbox_widget(width=800, height=600)
        result = letterbox_pil(widget, store, slot_index=0)

        assert result.size == (800, 600)
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0)) == (0, 0, 0, 0), "letterbox area must stay transparent"

        offset_x, offset_y, nw, nh = widget.runtime_state._letterbox_params[0]
        content_w = int(round(nw * 800))
        content_h = int(round(nh * 600))
        # 600x400 source in an 800x600 canvas is wider -> fits the width.
        assert content_w == 800
        assert 0 < content_h < 600
        assert offset_x == 0.0
        assert 0.0 < offset_y < 0.5, "content must be vertically letterboxed"
        # A pixel inside the pasted content region is opaque (not the padding color).
        inner_x = int(offset_x * 800) + 4
        inner_y = int(offset_y * 600) + 4
        assert result.getpixel((inner_x, inner_y))[3] == 255
    finally:
        store.close()