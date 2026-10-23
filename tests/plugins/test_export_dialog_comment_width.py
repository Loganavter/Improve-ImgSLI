"""Measuring the export layout must not resize the live form widgets.

The export geometry pass computes the dialog size from *hints*. Reading a
hint through ``adjustSize()`` (``shared_toolkit.ui.layout_sizing.widget_width_hint``
/ ``widget_height_hint``) resizes the widget to ``sizeHint()`` as a side
effect. ``CustomLineEdit``'s hint tracks its text, so an empty comment field
hint is its 40 px floor: every geometry pass — theme change, language switch,
format switch, app-font change — visibly collapsed the comment field to that
floor until Qt happened to re-run the parent layout.

The assertion is deliberately *synchronous*: no ``processEvents`` between the
measurement and the read, so a transient collapse cannot hide behind a
pending layout request.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from resources.translations import add_i18n_root


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _export_dialog(**overrides):
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState

    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    state = ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
    )
    kwargs = dict(dialog_state=state, suggested_filename="out")
    kwargs.update(overrides)
    return ExportDialog(**kwargs)


def _shown_dialog():
    host = QWidget()
    host.resize(1200, 800)
    host.show()
    dialog = _export_dialog(parent=host)
    dialog.show()
    for _ in range(3):
        QApplication.processEvents()
    return host, dialog


def test_compute_size_keeps_live_field_widths(qapp):
    """A pure measurement pass leaves laid-out widths untouched."""
    from plugins.export.layout_geometry import compute_export_dialog_size

    host, dialog = _shown_dialog()
    try:
        field_before = dialog.edit_comment.width()
        form_before = dialog.export_form_frame.width()
        # Sanity: the field is actually laid out wide before the pass.
        assert field_before > 200, field_before

        compute_export_dialog_size(dialog)

        assert dialog.edit_comment.width() == field_before, (
            "geometry measurement resized the comment field: "
            f"{field_before} -> {dialog.edit_comment.width()}"
        )
        assert dialog.export_form_frame.width() == form_before
    finally:
        dialog.close()
        dialog.deleteLater()
        host.close()
        host.deleteLater()


def test_geometry_apply_keeps_live_field_widths(qapp):
    """The full apply path keeps the laid-out field width (no collapse)."""
    host, dialog = _shown_dialog()
    try:
        # Widen the shell past the computed size: apply() then skips its own
        # resize, which is exactly the state where the measured-then-resized
        # field used to stay collapsed (the user-visible "any hiccup" case).
        dialog.resize(dialog.width() + 300, dialog.height())
        for _ in range(3):
            QApplication.processEvents()

        field_before = dialog.edit_comment.width()
        assert field_before > 200, field_before

        dialog._apply_dialog_geometry()

        assert dialog.edit_comment.width() == field_before, (
            f"apply collapsed the comment field {field_before} -> "
            f"{dialog.edit_comment.width()}"
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        host.close()
        host.deleteLater()
