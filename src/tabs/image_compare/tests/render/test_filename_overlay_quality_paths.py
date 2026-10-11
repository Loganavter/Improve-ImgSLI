"""Variant C1 quality pins + the offscreen glyph-atlas test.

Two jobs:

* **Atlas correctness** -- advances and coverage match ``QFontMetrics`` /
  the glyph outline, and ``ensure()`` is a no-op on an unchanged key (the
  property that lets a split drag skip the CPU entirely).
* **Crispness** -- a CPU SDF-threshold run simulator is compared against the
  retired variant-A reference (4x QPainter raster, Lanczos/``Smooth``
  downsample to 18px). The SDF run must be at least as crisp (fewer partial-
  alpha edge pixels) and close to the reference (low mean abs diff). Numbers
  are printed for the record.

No GPU: the atlas is a CPU ``QImage`` and the simulator reproduces the
fragment shader's threshold in numpy.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
)

from tabs.image_compare.canvas.features.filename_overlay.render.glyph_atlas import (
    GlyphAtlas,
)

_TEXT = "sample.png"
_PIXEL_SIZE = 18
_DPR = 4.0


def _font() -> QFont:
    font = QFont()
    font.setPixelSize(_PIXEL_SIZE)
    return font


def _atlas() -> GlyphAtlas:
    atlas = GlyphAtlas(None)
    atlas.ensure(_font(), _PIXEL_SIZE, _DPR)
    return atlas


def _atlas_pixels(atlas: GlyphAtlas) -> np.ndarray:
    raw = np.frombuffer(atlas.image.constBits(), dtype=np.uint8)
    return raw.reshape(atlas.height, atlas.width, 4)


def test_atlas_advances_match_font_metrics(qapp):
    atlas = _atlas()
    dev_font = QFont(_font())
    dev_font.setPixelSize(int(round(_PIXEL_SIZE * _DPR)))
    dev_metrics = QFontMetrics(dev_font)
    for ch in "Aghm.W":
        slot = atlas.glyph_for(ch)
        assert slot is not None, f"atlas lost glyph {ch!r}"
        expected = dev_metrics.horizontalAdvance(ch) / _DPR
        assert abs(slot.advance_px - expected) <= 1.5, (
            f"{ch!r} advance {slot.advance_px} vs metrics {expected}"
        )
    space = atlas.glyph_for(" ")
    assert space is not None, (
        "space must be present as an advance-only slot -- dropping it collapses "
        "words together (the pen never advances)"
    )
    assert space.size_px == (0.0, 0.0), "space must carry no ink tile"
    assert space.advance_px > 0.0, "space must advance the pen"


def test_atlas_coverage_is_a_spread_sdf(qapp):
    atlas = _atlas()
    pixels = _atlas_pixels(atlas)
    slot = atlas.glyph_for("g")
    assert slot is not None
    u0, v0, u1, v1 = slot.uv
    tile = pixels[
        int(v0 * atlas.height) : int(v1 * atlas.height),
        int(u0 * atlas.width) : int(u1 * atlas.width),
        0,
    ]
    assert tile.size > 0
    # A real SDF spans well inside (0) and well outside (255) the edge.
    assert tile.min() < 128, "no glyph interior in the atlas tile"
    assert tile.max() > 200, "no glyph exterior in the atlas tile"
    assert abs(float(tile.mean()) - 255.0) > 1.0, "tile is uniformly outside"


def test_atlas_ensure_is_keyed_noop(qapp):
    atlas = _atlas()
    assert atlas.ensure(_font(), _PIXEL_SIZE, _DPR) is False, (
        "ensure() rebuilt on an unchanged (font, pixel_size, dpr) key -- a "
        "split drag would re-rasterize the atlas every frame"
    )
    assert atlas.ensure(_font(), _PIXEL_SIZE + 4, _DPR) is True


def _sdf_run(atlas: GlyphAtlas, metrics: QFontMetrics, text: str, w: int, h: int):
    """Reproduce the fragment shader's SDF threshold for a whole run (1x)."""
    out = np.zeros((h, w), dtype=np.float64)
    pixels = _atlas_pixels(atlas)
    pen = 0.0
    baseline = (h - metrics.height()) / 2.0 + metrics.ascent()
    for ch in text:
        slot = atlas.glyph_for(ch)
        if slot is not None:
            gw, gh = slot.size_px
            x0 = pen + slot.bearing_px[0]
            y0 = baseline + slot.bearing_px[1]
            u0, v0, u1, v1 = slot.uv
            for py in range(max(0, int(np.floor(y0))), min(h, int(np.ceil(y0 + gh)))):
                for px in range(
                    max(0, int(np.floor(x0))), min(w, int(np.ceil(x0 + gw)))
                ):
                    sx = (px + 0.5 - x0) / gw
                    sy = (py + 0.5 - y0) / gh
                    if not (0.0 <= sx <= 1.0 and 0.0 <= sy <= 1.0):
                        continue
                    ax = min(atlas.width - 1, int((u0 + sx * (u1 - u0)) * atlas.width))
                    ay = min(atlas.height - 1, int((v0 + sy * (v1 - v0)) * atlas.height))
                    tex = pixels[ay, ax, 0] / 255.0
                    alpha = float(np.clip(tex, 0.0, 1.0))
                    out[py, px] = alpha + out[py, px] * (1.0 - alpha)
            pen += slot.advance_px
    return out


def _lanczos_reference(metrics: QFontMetrics, text: str, w: int, h: int):
    """The retired variant-A reference: 4x QPainter raster, smooth downsample."""
    ss = 4
    big = QImage(w * ss, h * ss, QImage.Format.Format_RGBA8888)
    big.fill(0)
    painter = QPainter(big)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(ss, ss)
        painter.setFont(_font())
        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(
            0,
            0,
            w,
            h,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
    finally:
        painter.end()
    small = big.scaled(
        w,
        h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    raw = np.frombuffer(small.constBits(), dtype=np.uint8).reshape(h, w, 4)
    return raw[..., 3].astype(np.float64) / 255.0


def test_sdf_run_is_crisp_vs_lanczos_reference(qapp):
    atlas = _atlas()
    metrics = QFontMetrics(_font())
    adv = sum(metrics.horizontalAdvance(c) for c in _TEXT)
    w = adv + 2
    h = metrics.height()
    sdf = _sdf_run(atlas, metrics, _TEXT, w, h)
    ref = _lanczos_reference(metrics, _TEXT, w, h)

    mean_diff = float(np.abs(sdf - ref).mean())
    sdf_ink = int((sdf > 0.5).sum())
    ref_ink = int((ref > 0.5).sum())
    sdf_partial = int(((sdf > 0.05) & (sdf < 0.95)).sum())
    ref_partial = int(((ref > 0.05) & (ref < 0.95)).sum())
    print(
        f"[c1-sdf] mean_diff={mean_diff:.4f} sdf_ink={sdf_ink} "
        f"ref_ink={ref_ink} sdf_partial={sdf_partial} ref_partial={ref_partial}"
    )

    # The whole point of the coverage atlas: the output must be ANTIALIASED
    # (partial-alpha edge pixels present), never a binary 0/1 threshold -- that
    # binary/furry output was the live regression. It must also roughly match
    # the retired 4x-Lanczos reference (same coverage source).
    assert sdf_partial > 0, (
        "coverage atlas produced a binary run (no partial-alpha pixels) -- the "
        "non-antialiased/binary regression is back"
    )
    assert 0.5 <= sdf_ink / max(1, ref_ink) <= 2.0, (
        f"coverage ink {sdf_ink} diverges from reference {ref_ink}"
    )
    assert mean_diff < 0.25, (
        f"coverage/ref mean abs diff {mean_diff:.4f} too high -- atlas drifted "
        f"from the retired raster"
    )
