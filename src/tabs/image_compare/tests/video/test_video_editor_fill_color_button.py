"""Video editor fit-content background color button."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


def test_update_fit_fill_color_button_sets_underline_color():
    from tabs.image_compare.plugins.video_editor.dialog_export import VideoEditorDialogExport

    captured: dict[str, QColor] = {}
    dialog = SimpleNamespace(
        fit_content_fill_color=QColor(120, 40, 200, 180),
        btn_fit_fill_color=SimpleNamespace(
            setUnderlineColor=lambda color: captured.update(value=QColor(color)),
        ),
    )
    VideoEditorDialogExport(dialog).update_fit_fill_color_button()

    assert captured["value"].red() == 120
    assert captured["value"].green() == 40
    assert captured["value"].blue() == 200
    assert captured["value"].alpha() == 180


def test_apply_fit_fill_color_updates_state():
    from tabs.image_compare.plugins.video_editor.dialog_export import VideoEditorDialogExport

    updates: list[str] = []
    dialog = SimpleNamespace(
        fit_content_fill_color=QColor(0, 0, 0, 255),
        _update_fit_fill_color_button=lambda: updates.append("underline"),
        persistence=SimpleNamespace(
            persist_export_settings=lambda: updates.append("persist"),
        ),
        fitContentFillColorChanged=SimpleNamespace(
            emit=lambda color: updates.append(("emit", QColor(color).alpha())),
        ),
    )
    export_ui = VideoEditorDialogExport(dialog)
    export_ui._apply_fit_fill_color(QColor(10, 20, 30, 40))

    assert dialog.fit_content_fill_color.alpha() == 40
    assert updates == ["underline", "persist", ("emit", 40)]


def test_on_fit_fill_color_clicked_uses_settings_color_picker():
    from tabs.image_compare.plugins.video_editor.dialog_export import VideoEditorDialogExport

    calls: list[dict[str, object]] = []
    settings_presenter = SimpleNamespace(
        show_color_picker=lambda **kwargs: calls.append(kwargs),
    )
    main_window_app = SimpleNamespace(
        presenter=SimpleNamespace(
            get_feature=lambda name: settings_presenter if name == "settings" else None,
        ),
    )
    dialog = SimpleNamespace(
        fit_content_fill_color=QColor(1, 2, 3, 4),
        main_window_app=main_window_app,
    )
    export_ui = VideoEditorDialogExport(dialog)
    export_ui.on_fit_fill_color_clicked()

    assert len(calls) == 1
    assert calls[0]["key"] == "video_fit_fill"
    assert calls[0]["title_key"] == "export.select_background_color"
    assert calls[0]["show_alpha"] is True
    assert calls[0]["parent_window"] is dialog
    assert QColor(calls[0]["current_color"]) == QColor(1, 2, 3, 4)


def test_color_picker_recenters_transient_parent_on_close():
    from PySide6.QtWidgets import QApplication, QDialog, QWidget

    from sli_ui_toolkit.theme import ThemeManager
    from tabs.image_compare.ui.settings_color_pickers import SettingsColorPickerCoordinator

    app = QApplication.instance() or QApplication([])
    main_window = QWidget()
    main_window.theme_manager = ThemeManager.get_instance()
    host = QDialog()
    host.show()
    activations: list[str] = []
    host.raise_ = lambda: activations.append("raise")  # type: ignore[method-assign]
    host.activateWindow = lambda: activations.append("activate")  # type: ignore[method-assign]

    coordinator = SettingsColorPickerCoordinator(
        store=SimpleNamespace(viewport=object()),
        main_controller=SimpleNamespace(settings=None),
        main_window_app=main_window,
        tr_func=lambda key: key,
    )
    coordinator.show_color_picker(
        key="test_host",
        current_color=QColor(10, 20, 30),
        title_key="export.select_background_color",
        on_selected=lambda _color: None,
        parent_window=host,
    )
    picker = coordinator._dialogs["test_host"]
    assert picker.parent() is host
    assert picker.windowModality() == Qt.WindowModality.WindowModal

    picker.close()
    app.processEvents()

    assert activations == ["raise", "activate"]
    host.close()
    picker.deleteLater()
    host.deleteLater()
    main_window.deleteLater()
    app.processEvents()
