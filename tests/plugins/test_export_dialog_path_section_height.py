"""Export dialog path row must not crush Browse / favorite buttons on height squeeze."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from ui.widgets.form_controls import OutputPathSection


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_output_path_section_resists_vertical_squeeze(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    section = OutputPathSection(
        directory_label_text="Dir:",
        browse_text="Browse...",
        set_favorite_text="Set as Favorite",
        use_favorite_text="Use Favorite",
        filename_label_text="File name:",
        use_custom_line_edit=False,
    )
    layout.addWidget(section)
    layout.addStretch(1)
    section.lock_content_minimum_height()

    host.resize(420, 400)
    host.show()
    qapp.processEvents()

    natural_h = section.height()
    assert natural_h >= section.minimumHeight()
    assert section.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum

    # Parent shorter than content: section must keep its minimum (not Preferred-crush).
    host.resize(420, max(80, natural_h // 3))
    qapp.processEvents()

    assert section.height() >= section.minimumHeight()
    fav_bottom = section.favorite_actions.geometry().bottom()
    assert fav_bottom <= section.height()
    assert section.btn_set_favorite.height() >= 28
    assert section.btn_browse_dir.height() >= 28


def test_export_dialog_keeps_path_buttons_when_height_forced(qapp, monkeypatch):
    from domain.types import Color
    from plugins.export.dialog import ExportDialog
    from plugins.export.models import ExportDialogState
    from resources.translations import add_i18n_root

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
    dialog = ExportDialog(dialog_state=state, suggested_filename="out")
    dialog.show()
    qapp.processEvents()

    section = dialog.output_section
    assert section.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum

    # Simulate compositor ignoring Qt minimum (CSD startSystemResize).
    dialog.setMinimumHeight(0)
    dialog.resize(dialog.width(), 420)
    qapp.processEvents()

    fav_bottom = section.btn_set_favorite.mapTo(
        section, section.btn_set_favorite.rect().bottomLeft()
    ).y()
    assert fav_bottom <= section.height()
    assert section.height() >= section.minimumHeight()

    action_bar = dialog.action_bar
    ab_bottom = action_bar.mapTo(
        dialog, action_bar.rect().bottomRight()
    ).y()
    assert ab_bottom <= dialog.height()
    assert action_bar.height() >= 32
    assert dialog.btn_ok.height() >= 28
    assert dialog.btn_cancel.height() >= 28
