"""Export fill-background gated on virtual canvas (scene beyond 0..1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from domain.types import Color
from plugins.export.dialog import ExportDialog
from plugins.export.models import ExportDialogState
from resources.translations import add_i18n_root
from tabs.image_compare.plugins.video_editor.services.video_export.models import (
    GlobalCanvasBounds,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _state(*, virtual_canvas_active: bool, fill_background: bool = True) -> ExportDialogState:
    return ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=fill_background,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=virtual_canvas_active,
    )


def test_global_canvas_bounds_extends_beyond_unit():
    unit = GlobalCanvasBounds(0, 0, 0, 0, 100, 100)
    assert unit.extends_beyond_unit() is False
    padded = GlobalCanvasBounds(10, 0, 0, 0, 100, 100, canvas_x_min=-0.1)
    assert padded.extends_beyond_unit() is True


def test_fill_checkbox_disabled_without_virtual_canvas(qapp):
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    dialog = ExportDialog(
        dialog_state=_state(virtual_canvas_active=False, fill_background=True),
        suggested_filename="out",
    )
    dialog.show()
    qapp.processEvents()

    assert dialog.checkbox_fill_bg.isEnabled() is False
    assert dialog.checkbox_fill_bg.isChecked() is False
    opts = dialog.get_export_options()
    assert opts["fill_background"] is False
    assert opts["fill_background_editable"] is False


def test_fill_checkbox_respects_settings_with_virtual_canvas(qapp):
    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    dialog = ExportDialog(
        dialog_state=_state(virtual_canvas_active=True, fill_background=True),
        suggested_filename="out",
    )
    dialog.show()
    qapp.processEvents()

    assert dialog.checkbox_fill_bg.isEnabled() is True
    assert dialog.checkbox_fill_bg.isChecked() is True
    opts = dialog.get_export_options()
    assert opts["fill_background"] is True
    assert opts["fill_background_editable"] is True
