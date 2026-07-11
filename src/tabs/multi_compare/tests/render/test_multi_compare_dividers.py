"""Multi-compare split dividers are explicit overlays, not incidental gaps."""

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
