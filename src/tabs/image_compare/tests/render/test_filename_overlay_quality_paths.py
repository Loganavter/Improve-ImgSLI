"""Variant A quality-path pins for the filename_overlay text raster.

Falsification story: these fail if the text-only raster stops being
supersampled, stops charging the caller's ``dpr``, or stops being a pure
function of content (the property that lets a split drag reuse the cached
texture instead of re-rasterizing on every width pixel).

No GPU, no scene: all checks are on the CPU ``QImage`` the raster returns.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QFont, QFontMetrics

from tabs.image_compare.canvas.features.filename_overlay.render.label_raster import (
    _LABEL_SUPERSAMPLE,
    rasterize_label_text,
)

_SHADERS = (
    Path(__file__).resolve().parents[2]
    / "canvas"
    / "features"
    / "filename_overlay"
    / "shaders"
)


def _font() -> QFont:
    return QFont()


def test_raster_charges_dpr_and_supersample(qapp):
    font = _font()
    metrics = QFontMetrics(font)
    text = "sample.png"
    rw = max(1, metrics.horizontalAdvance(text))
    rh = 26
    dpr = 2.0
    image, final_size = rasterize_label_text(
        text, rw, rh, font, metrics, QColor(255, 0, 0, 255), 0, dpr, _LABEL_SUPERSAMPLE
    )
    assert final_size == QSize(int(round(rw * dpr)), int(round(rh * dpr)))
    assert image.size() == QSize(
        int(round(rw * dpr * _LABEL_SUPERSAMPLE)),
        int(round(rh * dpr * _LABEL_SUPERSAMPLE)),
    )


def test_lanczos_scale_matches_raster_supersample():
    frag = (_SHADERS / "label_downsample.frag").read_text(encoding="utf-8")
    assert f"const float SCALE = {float(_LABEL_SUPERSAMPLE)}" in frag
    assert f"const int RADIUS = {int(2 * _LABEL_SUPERSAMPLE)}" in frag


def test_text_raster_is_transparent_background(qapp):
    font = _font()
    metrics = QFontMetrics(font)
    text = "sample.png"
    rw = max(1, metrics.horizontalAdvance(text))
    rh = 26
    image, _ = rasterize_label_text(
        text, rw, rh, font, metrics, QColor(255, 0, 0, 255), 0, 2.0, _LABEL_SUPERSAMPLE
    )
    assert image.pixelColor(0, 0).alpha() == 0, (
        "text-only raster has an opaque corner -- the background leaked back "
        "into the CPU raster (variant A moved it to filename_overlay.frag)"
    )
    alphas = [
        image.pixelColor(x, image.height() // 2).alpha()
        for x in range(0, image.width(), max(1, image.width() // 32))
    ]
    assert max(alphas) > 0, "text raster is fully transparent -- nothing drawn"
