"""Regression: mixed-size pair 2797x2304 vs 764x576 must not produce sliver gaps.

Bug 53,603: left 5x6=30 vs right 2x2=4, letterbox 0.499 vs 0.545 -> 6 narrow bboxes
0.00107 and 3 horizontal stripes. After fix union letterbox 1==2 and no narrow.
"""

from types import SimpleNamespace

from PIL import Image

from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer.draw_plan import build_array_draw_plan
from tabs.image_compare.canvas.texture_parts.base_images import update_common_letterbox_geometry


def _widget(width=1851, height=762):
    state = SimpleNamespace(
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
        _store=None,
    )
    return SimpleNamespace(runtime_state=state, width=lambda: width, height=lambda: height)


def test_mixed_size_union_letterbox_equal():
    widget = _widget()
    update_common_letterbox_geometry(
        widget,
        Image.new("RGBA", (2797, 2304)),
        Image.new("RGBA", (764, 576)),
    )
    lb0, lb1 = widget.runtime_state._letterbox_params
    assert lb0 == lb1, f"mixed-size must share one letterbox, got {lb0} vs {lb1}"
    # letterbox must be valid and not degenerate
    assert 0 <= lb0[0] < 1 and 0 <= lb0[1] < 1 and 0 < lb0[2] <= 1


def test_mixed_size_draw_plan_no_narrow():
    # Use union letterbox from previous helper to mimic fixed geometry
    widget = _widget()
    update_common_letterbox_geometry(
        widget,
        Image.new("RGBA", (2797, 2304)),
        Image.new("RGBA", (764, 576)),
    )
    lb = widget.runtime_state._letterbox_params[0]
    base_image = SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=lb,
        letterbox2=lb,
    )
    svc = TileTextureService(max_tile_extent=512)
    svc.register_source("s1", (2797, 2304))
    svc.register_source("s2", (764, 576))
    # mark all tiles resident
    for r in range(5):
        for c in range(6):
            # s1 5x6 approx (rows 5 cols 6) - mark superset to ensure hit
            try:
                svc.mark_resident("s1", (r, c), byte_size=100, content_size=(512, 512))
            except Exception:
                pass
    for r in range(2):
        for c in range(2):
            svc.mark_resident("s2", (r, c), byte_size=100, content_size=(512, 512))

    items = build_array_draw_plan(svc, ("s1", "s2"), base_image, diff_key=None, sampler_name="linear")
    assert items, "draw plan must not be empty for resident tiles"
    # No sliver: every bbox width/height >= 0.002 (draw_plan sliver filter)
    narrows = [it for it in items if it.bbox[2] < 0.002 or it.bbox[3] < 0.002]
    assert not narrows, f"mixed-size draw plan must have no sliver bboxes, got {len(narrows)}/{len(items)} narrow {[it.bbox for it in narrows[:3]]}"
    # Also check letterbox mismatch would have produced narrow - sanity: mismatched would be narrow
    # (not asserting here, just ensuring fixed path is clean)
