"""Multi-compare split dividers are explicit overlays, not incidental gaps."""

from PySide6.QtCore import QRectF

from tabs.multi_compare.canvas.features.grid_dividers.passes import fb_rect_to_ndc_quad
from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource


def test_divider_projection_uses_minimum_framebuffer_thickness():
    source = DividersOverlaySource()
    rect = source._project_gap(
        "h",
        (40, 0, 4, 200),
        0.25,
        (0.0, 0.0),
    )

    assert rect.width() == source.MIN_THICKNESS_FB


def test_fb_rect_to_ndc_quad_covers_full_framebuffer():
    packed = fb_rect_to_ndc_quad(QRectF(0.0, 0.0, 100.0, 50.0), 100.0, 50.0)
    assert len(packed) == 64
    # TL NDC
    import struct

    floats = struct.unpack("<16f", packed)
    assert floats[0:2] == (-1.0, 1.0)
    assert floats[4:6] == (-1.0, -1.0)
    assert floats[8:10] == (1.0, 1.0)
    assert floats[12:14] == (1.0, -1.0)
