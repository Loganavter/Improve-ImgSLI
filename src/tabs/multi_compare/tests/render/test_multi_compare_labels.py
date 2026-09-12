"""Multi-compare filename labels are camera-fixed bottom-layout elements."""

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont, QFontMetrics

from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource
from tabs.multi_compare.ui.layer_labels import LayerLabelStyle, layer_label_rect
from ui.canvas_presentation.filename_labels import fit_text


def test_label_style_is_framebuffer_fixed_not_canvas_scaled():
    source = LabelsOverlaySource()

    style = source._resolve_label_style()

    assert style.font_pixel_size_fb == 32
    assert style.safe_gap_fb == 8.0
    assert style.glyph_overscan_fb == 2.0


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


def test_label_does_not_elide_when_cell_has_room_with_fractional_padding(qapp):
    """Fractional DU padding + pixel snap used to shrink inner_w below advance.

    At short-edge ~720px, padding is 7.2 and preferred width snapped down so
    fit_text always elided even when the cell was wide enough for the full name.
    """
    style = LayerLabelStyle(
        font_pixel_size_fb=23,
        padding_x_fb=7.2,
        padding_y_fb=4.32,
        safe_gap_fb=5.76,
        text_inset_fb=7.2,
        glyph_overscan_fb=1.44,
    )
    text = "example.png"
    cell_w = 400.0

    rect = layer_label_rect(
        cell_rect_fb=(0.0, 0.0, cell_w, 300.0),
        text=text,
        style=style,
    )
    assert isinstance(rect, QRectF)

    font = QFont()
    font.setPixelSize(style.font_pixel_size_fb)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    fm = QFontMetrics(font)
    advance = float(fm.horizontalAdvance(text))

    assert rect.width() >= advance + style.padding_x_fb * 2.0
    inner_w = rect.width() - style.text_inset_fb * 2.0
    assert fit_text(text, fm, inner_w) == text


def test_scaled_label_style_includes_glyph_overscan():
    source = LabelsOverlaySource()
    style = source._resolve_label_style(short_edge_fb=720.0)

    assert style.padding_x_fb == pytest.approx(7.2)
    assert style.glyph_overscan_fb == pytest.approx(1.44)
    assert style.text_inset_fb == pytest.approx(7.2)
