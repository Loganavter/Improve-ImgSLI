"""Variant C1 reuse pins: the atlas is content-keyed, not width-keyed.

Falsification story: these fail if ``pack_run`` grows a label-quad width
parameter (re-coupling the packed run to the split drag) or stops being a
deterministic pure function of ``(text, atlas, origin, color, weight, scale)``,
or if ``GlyphAtlas.ensure`` re-rasterizes when the ``(font, pixel_size, dpr)``
key is unchanged.

The companion boundary test
(``test_filename_boundary.py::test_filename_passes_pack_runs_and_draw_n_quads``)
pins the ``prepare()`` flow at the AST level; this file pins the functions a
split drag actually re-invokes.

No GPU: the atlas is pure CPU ``QImage`` work.
"""

from __future__ import annotations

import inspect

from PySide6.QtGui import QFont

from tabs.image_compare.canvas.features.filename_overlay.render.glyph_atlas import (
    GlyphAtlas,
)
from tabs.image_compare.canvas.features.filename_overlay.render.text_run import (
    pack_bg_quad,
    pack_run,
)

_COLOR = (1.0, 0.0, 0.0, 1.0)
_PIXEL_SIZE = 18
_LARGER_PIXEL_SIZE = 24


def _font() -> QFont:
    font = QFont()
    font.setPixelSize(_PIXEL_SIZE)
    return font


def _atlas() -> GlyphAtlas:
    atlas = GlyphAtlas(None)
    atlas.ensure(_font(), _PIXEL_SIZE, 2.0)
    return atlas


def test_pack_run_is_deterministic(qapp):
    atlas = _atlas()
    first, n1 = pack_run("hello.png", atlas, (10.0, 30.0), _COLOR, 0, 1.0)
    second, n2 = pack_run("hello.png", atlas, (10.0, 30.0), _COLOR, 0, 1.0)
    assert n1 == n2 == len("hello.png")
    assert first == second


def test_pack_run_empty_text(qapp):
    atlas = _atlas()
    data, count = pack_run("", atlas, (0.0, 0.0), _COLOR, 0, 1.0)
    assert data == b"" and count == 0


def test_pack_run_scales_geometry_not_uv(qapp):
    atlas = _atlas()
    one, _ = pack_run("a", atlas, (0.0, 0.0), _COLOR, 0, 1.0)
    two, _ = pack_run("a", atlas, (0.0, 0.0), _COLOR, 0, 2.0)
    assert one != two, "pack_run ignored the zoom scale"


def test_pack_run_api_has_no_label_quad_width_parameter():
    params = list(inspect.signature(pack_run).parameters)
    assert params == [
        "text",
        "atlas",
        "origin_px",
        "color_rgba",
        "weight",
        "scale",
    ]
    assert "quad_w" not in params and "label_width" not in params, (
        "pack_run gained a label-quad width input -- a split drag would repack "
        "against the width; re-open the C1 design"
    )


def test_pack_bg_quad_has_no_glyph_quads():
    verts = pack_bg_quad((0.0, 0.0, 100.0, 20.0))
    # 6 vertices * 40-byte stride, one quad.
    assert len(verts) == 6 * 40


def test_atlas_key_ignores_label_width(qapp):
    atlas = _atlas()
    first = atlas.ensure(_font(), _PIXEL_SIZE, 2.0)
    assert first is False, "atlas rebuilt without a key change"
    # Rebuilding for a font change is expected and must produce a new atlas.
    other = QFont()
    other.setPixelSize(_LARGER_PIXEL_SIZE)
    assert atlas.ensure(other, _LARGER_PIXEL_SIZE, 2.0) is True
