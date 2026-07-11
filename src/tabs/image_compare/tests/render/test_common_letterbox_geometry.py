"""Both comparison textures share one letterbox transform."""

from types import SimpleNamespace

from PIL import Image

from tabs.image_compare.canvas.texture_parts.base_images import (
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

    assert state._letterbox_params[0] == state._letterbox_params[1]
    assert state._letterbox_params[0] == (0.0, 0.0, 1.0, 1.0)
    assert state._content_rect_px == (0, 0, 1000, 500)
