"""Variant A reuse pins: the text raster is content-keyed, not width-keyed.

Falsification story: these fail if ``rasterize_label_text`` grows a
label-quad width parameter (re-coupling raster to the split drag) or stops
being a deterministic pure function of ``(name, rw, rh, dpr, supersample)``.

The companion boundary test
(``test_filename_boundary.py::test_filename_raster_key_excludes_width_and_uniforms_are_per_slot``)
pins the ``prepare()`` cache key at the AST level; this file pins the
function the key guards.

No GPU: the raster is pure CPU ``QImage`` work.
"""

from __future__ import annotations

import inspect

from PySide6.QtGui import QColor, QFont, QFontMetrics

from tabs.image_compare.canvas.features.filename_overlay.render.label_raster import (
    _LABEL_SUPERSAMPLE,
    rasterize_label_text,
)


def _font() -> QFont:
    return QFont()


def _raster(text: str, rw: int, rh: int, dpr: float):
    font = _font()
    return rasterize_label_text(
        text,
        rw,
        rh,
        font,
        QFontMetrics(font),
        QColor(255, 0, 0, 255),
        0,
        dpr,
        _LABEL_SUPERSAMPLE,
    )


def test_raster_is_content_deterministic(qapp):
    first_img, first_size = _raster("hello.png", 60, 26, 2.0)
    second_img, second_size = _raster("hello.png", 60, 26, 2.0)
    assert first_size == second_size
    assert first_img == second_img


def test_raster_dpr_is_part_of_the_content(qapp):
    _, size_1x = _raster("hello.png", 60, 26, 1.0)
    _, size_2x = _raster("hello.png", 60, 26, 2.0)
    assert size_2x.width() == 2 * size_1x.width()
    assert size_2x.height() == 2 * size_1x.height()


def test_raster_api_has_no_label_quad_width_parameter():
    params = list(inspect.signature(rasterize_label_text).parameters)
    assert params == [
        "name",
        "rw",
        "rh",
        "font",
        "metrics",
        "text_color",
        "font_weight",
        "dpr",
        "supersample",
    ]
    assert "quad_w" not in params and "label_width" not in params, (
        "rasterize_label_text gained a label-quad width input -- a split drag "
        "would re-rasterize again; re-open the variant-A design"
    )
