"""CSD rounded mask must use logical QRegion (HiDPI-safe)."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.windows.rounded_body import (
    apply_rounded_window_mask,
    rounded_window_path,
)


def test_rounded_window_mask_uses_region_not_bitmap():
    QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.resize(400, 300)
    widget.show()
    QApplication.processEvents()

    apply_rounded_window_mask(widget, radius=10.0, squared=False)
    mask = widget.mask()
    assert isinstance(mask, QRegion)
    assert not mask.isEmpty()

    # Corner outside the rounded silhouette must be excluded.
    assert not mask.contains(widget.rect().topLeft())
    assert mask.contains(widget.rect().center())

    expected = QRegion(
        rounded_window_path(
            QRectF(widget.rect()), radius=10.0, squared=False
        )
        .toFillPolygon()
        .toPolygon()
    )
    assert mask.boundingRect() == expected.boundingRect()
