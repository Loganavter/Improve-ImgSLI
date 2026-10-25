"""Export dialog preview geometry fallback (regression: undefined ``export_geo``).

``ExportDialog._apply_preview_pixmap`` resolves the scale target in three steps:
the label's live size, then its minimum size, then the design-px floor from
``plugins.export.layout_geometry``. That third step referenced ``export_geo``,
which ``dialog.py`` never imported (ruff F821), so any path that emptied both
the size and the minimum raised ``NameError`` instead of scaling.

The floor is the documented source of truth (``docs/dev/DIALOGS.md`` — read the
design px through the call-time resolver, never a copied constant), so the fix
restores the same ``layout_geometry as export_geo`` alias the widget builders in
``dialog_sections.py`` use. This test drives the fallback directly by emptying
the label, which is what the branch exists for.

Audit-Meta: task-export-geo-nameerror-2026-10-25
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from domain.types import Color
from plugins.export import layout_geometry as export_geo
from plugins.export.dialog import ExportDialog
from plugins.export.models import ExportDialogState
from resources.translations import add_i18n_root


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


def test_preview_falls_back_to_geometry_floor(qapp):
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    width = export_geo.export_preview_min_width()
    height = export_geo.export_preview_min_height()
    source = QPixmap(width, height)
    source.fill(QColor(10, 120, 200, 255))

    dialog = ExportDialog(
        dialog_state=_state(),
        suggested_filename="out",
        preview_image=source,
    )
    try:
        # Force the third branch: no live size and no label minimum left.
        dialog.preview_label.setMinimumSize(QSize(0, 0))
        dialog.preview_label.resize(0, 0)
        assert dialog.preview_label.size().isEmpty()
        assert dialog.preview_label.minimumSize().isEmpty()

        dialog._apply_preview_pixmap()

        pixmap = dialog.preview_label.pixmap()
        assert not pixmap.isNull()
        assert pixmap.size() == QSize(width, height)
    finally:
        dialog.deleteLater()


def test_preview_uses_live_label_size_when_available(qapp):
    """Working sibling: the same call must stay off the fallback when sized."""
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    width = export_geo.export_preview_min_width()
    height = export_geo.export_preview_min_height()
    source = QPixmap(width, height)
    source.fill(QColor(10, 120, 200, 255))

    dialog = ExportDialog(
        dialog_state=_state(),
        suggested_filename="out",
        preview_image=source,
    )
    try:
        smaller = QSize(width // 2, height // 2)
        dialog.preview_label.setMinimumSize(QSize(0, 0))
        dialog.preview_label.resize(smaller)
        assert not dialog.preview_label.size().isEmpty()

        dialog._apply_preview_pixmap()

        pixmap = dialog.preview_label.pixmap()
        assert not pixmap.isNull()
        assert pixmap.size() == smaller
    finally:
        dialog.deleteLater()
