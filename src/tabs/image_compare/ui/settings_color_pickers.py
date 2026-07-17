from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QWidget

from domain.qt_adapters import color_to_qcolor, qcolor_to_color
from ui.canvas_infra.scene.property_access import read_canvas_feature_color_by_setting_key
from ui.theming import polish_themed_dialog


class SettingsColorPickerCoordinator:
    def __init__(self, store, main_controller, main_window_app, tr_func):
        self.store = store
        self.main_controller = main_controller
        self.main_window_app = main_window_app
        self.tr = tr_func
        self._dialogs: dict[str, QColorDialog | None] = {}

    def show_canvas_feature_color_picker(
        self,
        *,
        key: str,
        setting_key: str,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
    ):
        self._show_dialog(
            key=key,
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                setting_key,
            ),
            title_key=title_key,
            on_selected=on_selected,
            post_apply=post_apply,
        )

    def show_magnifier_divider_color_picker(self):
        self._show_dialog(
            key="magnifier_divider",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "magnifier.divider.color",
            ),
            title_key="ui.choose_magnifier_divider_line_color",
            on_selected=self._apply_magnifier_divider_color,
        )

    def show_magnifier_border_color_picker(self):
        self._show_dialog(
            key="magnifier_border",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "magnifier.border.color",
            ),
            title_key="ui.choose_magnifier_border_color",
            on_selected=self._apply_magnifier_border_color,
        )

    def show_laser_color_picker(self):
        self._show_dialog(
            key="laser",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "guides.color",
            ),
            title_key="ui.choose_magnifier_guides_color",
            on_selected=self._apply_guides_color,
        )

    def show_capture_ring_color_picker(self):
        self._show_dialog(
            key="capture_ring",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "capture.color",
            ),
            title_key="ui.choose_capture_ring_color",
            on_selected=self._apply_capture_color,
        )

    def show_color_picker(
        self,
        *,
        key: str,
        current_color,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
        show_alpha: bool = False,
        parent_window: QWidget | None = None,
    ) -> None:
        """Open a themed picker for an arbitrary color (not store-backed)."""
        self._show_dialog(
            key=key,
            current_color=current_color,
            title_key=title_key,
            on_selected=on_selected,
            post_apply=post_apply,
            show_alpha=show_alpha,
            parent_window=parent_window,
        )

    def apply_smart_magnifier_colors(self):
        key = "smart_magnifier"
        existing = self._dialogs.get(key)
        if existing and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        dialog = QColorDialog(
            color_to_qcolor(
                read_canvas_feature_color_by_setting_key(
                    "image_compare",
                    self.store.viewport,
                    "magnifier.divider.color",
                )
            ),
            self.main_window_app,
        )
        dialog.setModal(False)
        dialog.setWindowTitle(self.tr("ui.choose_magnifier_base_color"))
        polish_themed_dialog(self.main_window_app.theme_manager, dialog)

        def on_color_selected(color):
            if not color.isValid():
                return

            border_color = QColor(color)
            border_color.setAlpha(230)

            capture_ring_color = QColor(color)
            capture_ring_color.setAlpha(230)

            settings_controller = self._settings_controller()
            if settings_controller is None:
                return

            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_border_color",
                qcolor_to_color(border_color),
            )
            settings_controller.execute_canvas_feature_alias(
                "guides.settings.set_color",
                qcolor_to_color(QColor(color)),
            )
            settings_controller.execute_canvas_feature_alias(
                "capture.settings.set_color",
                qcolor_to_color(capture_ring_color),
            )

        dialog.colorSelected.connect(on_color_selected)
        dialog.finished.connect(lambda _result, k=key: self._dialogs.pop(k, None))
        dialog.show()
        self._dialogs[key] = dialog

    def _show_dialog(
        self,
        *,
        key: str,
        current_color,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
        show_alpha: bool = False,
        parent_window: QWidget | None = None,
    ):
        dialog = self._dialogs.get(key)
        if dialog and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return

        host = parent_window if parent_window is not None else self.main_window_app
        dialog = QColorDialog(color_to_qcolor(current_color), host)
        if show_alpha:
            dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowFlags(dialog.windowFlags() | 0x00000000)
        if parent_window is not None:
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
        else:
            dialog.setModal(False)
        dialog.setWindowTitle(self.tr(title_key))
        polish_themed_dialog(self.main_window_app.theme_manager, dialog)

        def handle_selected(color):
            if not color.isValid():
                return
            on_selected(color)
            if post_apply is not None:
                post_apply(color)

        def on_finished(_result, *, dialog_key=key, transient_host=parent_window):
            self._dialogs.pop(dialog_key, None)
            if transient_host is None:
                return
            try:
                if transient_host.isVisible():
                    transient_host.raise_()
                    transient_host.activateWindow()
            except RuntimeError:
                return

        dialog.colorSelected.connect(handle_selected)
        dialog.finished.connect(on_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._dialogs[key] = dialog

    def _apply_magnifier_divider_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_divider_color",
                qcolor_to_color(color),
            )

    def _apply_magnifier_border_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_border_color",
                qcolor_to_color(color),
            )

    def _apply_capture_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "capture.settings.set_color",
                qcolor_to_color(color),
            )

    def _apply_guides_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "guides.settings.set_color",
                qcolor_to_color(color),
            )

    def _settings_controller(self):
        return getattr(self.main_controller, "settings", None)
