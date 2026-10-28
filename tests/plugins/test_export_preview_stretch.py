"""The export preview must *stretch*, not re-create itself on every resize frame.

Owner report (2026-10-28): «почему-то ресайз превьювера сделан очень криво —
вместо растягивания его будто просто убивают и заново создают каждый кадр»,
with the working sibling named by the owner: «на главном окне в табах сравнения
и мультисравнения тот же холст нормально ресайзится».

Cause: ``ExportDialog`` ran ``QPixmap.scaled(SmoothTransformation)`` on the
full-size preview source from ``resizeEvent`` (both the settle and pulse
callbacks pointed at ``_apply_preview_pixmap``) and handed every result to
``QLabel.setPixmap`` — one brand-new bitmap per resize frame. The compare
canvases look right because they draw their scene at the *current* size every
paint; the fix gives the pane the same model: keep the source, draw it
aspect-fitted into the live contents rect in ``paintEvent``, and bake one smooth
raster only when the resize settles (keyed, so a stale bake is never painted at
another size).

Discriminator used below: a resize burst must not replace the label's raster
(old code: a different ``QPixmap.cacheKey()`` per frame). The second test is the
anti-vacuity partner — "no raster swap" would also pass if nothing were painted,
so it renders the pane and requires the image to occupy the aspect-fitted box at
every intermediate size.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from domain.types import Color
from plugins.export.dialog import ExportDialog
from plugins.export.models import ExportDialogState
from resources.translations import add_i18n_root

_SOURCE_COLOR = QColor(255, 0, 255, 255)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _state() -> ExportDialogState:
    return ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=False,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=True,
    )


def _dialog(qapp, source_size: QSize = QSize(3840, 2160)) -> ExportDialog:
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    source = QPixmap(source_size)
    source.fill(_SOURCE_COLOR)
    dialog = ExportDialog(
        dialog_state=_state(),
        suggested_filename="out",
        preview_image=source,
    )
    dialog.show()
    qapp.processEvents()
    return dialog


def _painted_bbox(image: QImage, color: QColor, tol: int = 60) -> QRect:
    """Bounding box of pixels close to *color* (the preview's own pixels)."""
    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (
                pixel.alpha() > 200
                and abs(pixel.red() - color.red()) <= tol
                and abs(pixel.green() - color.green()) <= tol
                and abs(pixel.blue() - color.blue()) <= tol
            ):
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0 or bottom < 0:
        return QRect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


def _assert_bbox_matches(rect: QRect, expected: QRect) -> None:
    assert not rect.isEmpty(), "the pane painted nothing at all"
    assert abs(rect.x() - expected.x()) <= 2, (rect, expected)
    assert abs(rect.y() - expected.y()) <= 2, (rect, expected)
    assert abs(rect.width() - expected.width()) <= 2, (rect, expected)
    assert abs(rect.height() - expected.height()) <= 2, (rect, expected)


def test_resize_burst_does_not_rebake_the_preview_raster(qapp):
    """Red on the pre-fix tree: one new QPixmap per resize frame."""
    dialog = _dialog(qapp)
    try:
        label = dialog.preview_label
        width, height = dialog.width(), dialog.height()
        rasters: list = []
        for step in range(8):
            dialog.resize(width + step * 7, height + step * 5)
            qapp.processEvents()
            pixmap = label.pixmap()
            rasters.append(None if pixmap.isNull() else pixmap.cacheKey())

        assert len(set(rasters)) == 1, (
            "the preview raster was replaced on every resize frame "
            f"({len(set(rasters))} distinct rasters over {len(rasters)} frames); "
            "the pane must stretch its source instead of re-creating it"
        )
    finally:
        dialog.close()
        dialog.deleteLater()


def test_preview_stretches_into_every_intermediate_size(qapp):
    """Anti-vacuity partner: the pane really paints, fitted, at each size."""
    dialog = _dialog(qapp)
    try:
        label = dialog.preview_label
        wide, tall = label.minimumWidth(), label.minimumHeight()
        # Three different aspects, never below the pane minimum (Qt clamps it).
        for size in (
            QSize(wide, tall + 100),
            QSize(wide + 200, tall),
            QSize(wide + 120, tall + 120),
        ):
            label.resize(size)
            qapp.processEvents()
            image = label.grab().toImage()
            assert image.size() == label.size(), (image.size(), label.size())
            _assert_bbox_matches(
                _painted_bbox(image, _SOURCE_COLOR), label.preview_target_rect()
            )
    finally:
        dialog.close()
        dialog.deleteLater()


def test_settled_size_bakes_one_frame_and_a_stale_bake_is_not_painted(qapp):
    dialog = _dialog(qapp)
    try:
        label = dialog.preview_label
        width, height = dialog.width(), dialog.height()
        # A real resize goes through the dialog: its resizeEvent pings the
        # settle gate (resizing the label alone does not).
        dialog.resize(width + 60, height + 40)
        qapp.processEvents()
        dialog._preview_resize_settle.flush()
        qapp.processEvents()

        settled = label.preview_target_rect()
        assert label.baked_preview_size() == settled.size(), (
            "the quiet-period bake must rasterize the settled target size"
        )

        # Grow again without letting the gate fire: the old raster is stale and
        # must not be drawn (nor stretched by QLabel).
        dialog.resize(width + 140, height + 20)
        qapp.processEvents()
        grown = label.preview_target_rect()
        assert grown.size() != settled.size()
        assert label.baked_preview_size() == settled.size(), "no new bake before settling"
        image = label.grab().toImage()
        _assert_bbox_matches(_painted_bbox(image, _SOURCE_COLOR), grown)
    finally:
        dialog.close()
        dialog.deleteLater()
