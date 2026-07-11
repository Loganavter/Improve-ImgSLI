"""Multi-compare filename labels are camera-fixed bottom-layout elements."""

from PySide6.QtCore import QRectF

from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource
from tabs.multi_compare.ui.layer_labels import LayerLabelStyle, layer_label_rect


def test_label_style_is_framebuffer_fixed_not_canvas_scaled():
    source = LabelsOverlaySource()

    style = source._resolve_label_style()

    assert style.font_pixel_size_fb == 32
    assert style.safe_gap_fb == 8.0


def test_label_rect_anchors_to_bottom_left_of_cell(qapp):
    style = LayerLabelStyle(
        font_pixel_size_fb=32,
        padding_x_fb=14.0,
        padding_y_fb=7.0,
        safe_gap_fb=8.0,
    )

    rect = layer_label_rect(
        cell_rect_fb=(100.0, 200.0, 400.0, 300.0),
        text="example.png",
        style=style,
    )

    assert isinstance(rect, QRectF)
    assert rect.left() == 108.0
    assert rect.bottom() == 492.0


def test_long_label_is_width_limited_by_cell_pixels_not_character_count(qapp):
    style = LayerLabelStyle(
        font_pixel_size_fb=32,
        padding_x_fb=14.0,
        padding_y_fb=7.0,
        safe_gap_fb=8.0,
    )

    rect = layer_label_rect(
        cell_rect_fb=(0.0, 0.0, 160.0, 120.0),
        text="very-long-file-name-that-should-not-be-character-truncated.png",
        style=style,
    )

    assert isinstance(rect, QRectF)
    assert rect.width() == 144.0
