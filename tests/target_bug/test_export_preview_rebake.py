"""Target bug: the export preview re-creates its raster on every resize frame.

Bug row: "Export dialog preview is killed and re-created on every resize frame"
(``docs/bugs/README.md`` → ``bug.export_preview_rebake``).

Observed at the branch base (``c413564f0``): ``SettleGate`` in
``plugins/export/dialog.py`` had ``on_pulse`` and ``on_settle`` pointing at the
same ``_apply_preview_pixmap``, which ran ``QPixmap.scaled(SmoothTransformation)``
on the full-size preview source and handed the result to ``QLabel.setPixmap``.
One brand-new raster per resize frame is not a stretch: the pane popped instead
of following the window edge (owner report 2026-10-28; the working sibling is the
compare canvas, which draws its scene at the *current* size every paint).

The probe uses only the observable both sides share — the label's own raster
after each resize frame — so it reproduces on the pre-fix tree and reports
``fixed`` after the pane started stretching its source in ``paintEvent``
(``plugins/export/preview_pane.py``). The second half is the anti-vacuity
partner: "no raster swap" would also pass if nothing were painted at all, so the
fixed branch requires the image to occupy the aspect-fitted box.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from core.evidence.journal import record_evidence, reset_journal, verdict
from domain.types import Color
from plugins.export.dialog import ExportDialog
from plugins.export.models import ExportDialogState
from resources.translations import add_i18n_root

BUG_ID = "bug.export_preview_rebake"
_SOURCE_COLOR = QColor(255, 0, 255, 255)
_FRAMES = 8


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _fresh_journal():
    reset_journal()
    yield
    reset_journal()


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


def _dialog(qapp) -> ExportDialog:
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    source = QPixmap(QSize(3840, 2160))
    source.fill(_SOURCE_COLOR)
    dialog = ExportDialog(
        dialog_state=_state(),
        suggested_filename="out",
        preview_image=source,
    )
    dialog.show()
    qapp.processEvents()
    return dialog


def _painted_fraction(image, color: QColor, tol: int = 60) -> float:
    """Share of the grabbed pane covered by the preview's own pixels."""
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return 0.0
    hits = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (
                pixel.alpha() > 200
                and abs(pixel.red() - color.red()) <= tol
                and abs(pixel.green() - color.green()) <= tol
                and abs(pixel.blue() - color.blue()) <= tol
            ):
                hits += 1
    return hits / float(image.width() * image.height())


def test_export_preview_repro_and_fix(qapp) -> None:
    dialog = _dialog(qapp)
    try:
        label = dialog.preview_label
        width, height = dialog.width(), dialog.height()
        rasters: list = []
        for step in range(_FRAMES):
            dialog.resize(width + step * 7, height + step * 5)
            qapp.processEvents()
            pixmap = label.pixmap()
            rasters.append(None if pixmap.isNull() else pixmap.cacheKey())

        distinct = len(set(rasters))
        label.resize(label.width() + 40, label.height() + 20)
        qapp.processEvents()
        painted = _painted_fraction(label.grab().toImage(), _SOURCE_COLOR)
        signal = (
            f"resize_frames={_FRAMES} distinct_rasters={distinct} "
            f"painted_fraction={painted:.2f}"
        )
        ids = (
            "plugins/export/dialog.py::_apply_preview_pixmap",
            "plugins/export/preview_pane.py::ExportPreviewLabel.paintEvent",
        )

        if distinct > 1:
            record_evidence(
                BUG_ID,
                kind="target_bug",
                verdict="reproduced",
                signal=signal,
                reason=(
                    "every resize frame replaced the label's raster (a new "
                    "QPixmap per frame), so the preview was re-created instead "
                    "of stretched"
                ),
                ids=ids,
                area="plugins.export.preview_pane",
            )
            pytest.fail(f"reproduced: {signal}")

        # Anti-vacuity: "no raster swap" must not pass on an empty pane.
        if painted <= 0.05:
            record_evidence(
                BUG_ID,
                kind="target_bug",
                verdict="reproduced",
                signal=signal,
                reason=(
                    "the pane stopped swapping rasters but painted (almost) "
                    "nothing - the source is not drawn at the current size"
                ),
                ids=ids,
                area="plugins.export.preview_pane",
            )
            pytest.fail(f"reproduced (blank pane): {signal}")

        record_evidence(
            BUG_ID,
            kind="target_bug",
            verdict="fixed",
            signal=signal,
            reason=(
                "one source raster for the whole resize burst and the image is "
                "painted aspect-fitted into the live pane size"
            ),
            ids=ids,
            area="plugins.export.preview_pane",
        )
        assert verdict(None, BUG_ID).verdict == "fixed"
    finally:
        dialog.close()
        dialog.deleteLater()
