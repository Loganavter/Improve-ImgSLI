"""Dialog chrome regressions (task-fix-dialog-chrome-2026-09-20).

- Export line edits are TabFocus-capable (keyboard traversal works).
- Neither Settings nor Image-Properties dialog shadows ``QObject.tr``.
- Help dialog unregisters its NavigationManager sections on destroy.
- QWindow minimum is pinned after show; export re-pins after applies.
- Export dialog is parented to the shell (via DialogManager).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
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


def _export_line_edits(dialog):
    return [
        dialog.edit_dir,
        dialog.edit_name,
        dialog.edit_width,
        dialog.edit_height,
        dialog.edit_comment,
    ]


def test_export_line_edits_tab_focus_capable(qapp):
    dialog = _export_dialog()
    try:
        for edit in _export_line_edits(dialog):
            assert edit.focusPolicy() & Qt.FocusPolicy.TabFocus, (
                f"{edit.objectName() or type(edit).__name__} is not Tab-focusable"
            )
    finally:
        dialog.close()
        dialog.deleteLater()


def test_export_tab_traversal_moves_focus(qapp):
    dialog = _export_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        edits = _export_line_edits(dialog)
        edits[0].setFocus(Qt.FocusReason.TabFocusReason)
        qapp.processEvents()
        assert qapp.focusWidget() is edits[0]
        moved = dialog.focusNextPrevChild(True)
        qapp.processEvents()
        assert moved
        assert qapp.focusWidget() is not edits[0]
    finally:
        dialog.close()
        dialog.deleteLater()


def test_no_tr_shadow_on_settings_and_properties_dialogs(qapp):
    from plugins.image_properties.dialog import ImagePropertiesDialog
    from plugins.image_properties.service import ImageProperties
    from plugins.settings.dialog import SettingsDialog

    settings = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_compare",
    )
    props = ImagePropertiesDialog(
        ImageProperties(title="Properties", sections=()),
        parent=None,
        current_language="en",
    )
    try:
        for dialog in (settings, props):
            # No instance attribute shadowing QObject.tr.
            assert "tr" not in dialog.__dict__, (
                f"{type(dialog).__name__} shadows QObject.tr"
            )
            assert callable(getattr(dialog, "_tr_func", None))
            assert callable(getattr(dialog, "_tr", None))
        # The renamed channel still translates.
        assert settings._tr("common.ok", "en") != ""
        assert props._tr("image_properties.close", "Close") != ""
    finally:
        settings.close()
        settings.deleteLater()
        props.close()
        props.deleteLater()


def test_help_nav_unregistered_on_destroy(qapp):
    from sli_ui_toolkit.managers import NavigationManager

    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog(current_language="en", app_name="Test", parent=None)
    mgr = NavigationManager.get_instance()
    owners = [
        dialog._back_bar,
        getattr(dialog.shell, "sidebar_column", None) or dialog.nav_widget,
        dialog._content_host,
    ]
    try:
        registered = [o for o, _ in mgr._sections]
        assert any(o is owner for owner in owners for o in registered), (
            "help navigation sections were never registered"
        )
    finally:
        dialog.deleteLater()
    qapp.processEvents()
    remaining = [o for o, _ in mgr._sections]
    for owner in owners:
        assert all(o is not owner for o in remaining), (
            "help navigation owner leaked after destroy"
        )


def test_qwindow_minimum_pinned_after_show_and_export_repin(qapp):
    dialog = _export_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        handle = dialog.windowHandle()
        assert handle is not None
        assert handle.minimumSize() == dialog.minimumSize()

        # Visibility toggles (format switch) change the widget minimum;
        # the QWindow minimum must be re-pinned, not left stale.
        idx = dialog.combo_format.findText("JPEG")
        if idx >= 0:
            dialog.combo_format.setCurrentIndex(idx)
            qapp.processEvents()
            handle = dialog.windowHandle()
            assert handle is not None
            assert handle.minimumSize() == dialog.minimumSize()
    finally:
        dialog.close()
        dialog.deleteLater()


def test_export_dialog_parented_to_shell(qapp):
    from types import SimpleNamespace

    from ui.managers.dialog_manager import DialogManager

    shell = QWidget()
    host = SimpleNamespace(parent_widget=shell)
    manager = DialogManager(host)

    # Non-modal (2026-10-28): the manager returns the live dialog instead of a
    # (code, options) tuple from a blocking exec(); parenting is unchanged.
    dialog = manager.show_export_dialog(
        dialog_state=SimpleNamespace(
            output_dir="/tmp",
            favorite_dir=None,
            last_format="PNG",
            quality=95,
            png_compress_level=9,
            fill_background=False,
            background_color=None,
            comment_text="",
            comment_keep_default=False,
            resolution_scale=1.0,
            current_language="en",
            virtual_canvas_active=False,
        ),
        preview_image=None,
        suggested_filename="out",
    )
    assert dialog.parent() is shell
    dialog.close()
    dialog.deleteLater()
    shell.deleteLater()
