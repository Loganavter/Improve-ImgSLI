

import logging
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog

from core.store import Store
from core.constants import AppConstants
from core.events import (
    SettingsSetDividerLineColorEvent,
    SettingsSetMagnifierDividerColorEvent,
)
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class SettingsPresenter(QObject):

    def __init__(
        self,
        store: Store,
        main_controller,
        ui_manager,
        main_window_app,
        parent=None
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui_manager = ui_manager
        self.main_window_app = main_window_app

        self._divider_color_dialog = None
        self._magnifier_divider_color_dialog = None
        self._magnifier_border_color_dialog = None
        self._magnifier_laser_color_dialog = None
        self._capture_ring_color_dialog = None

    def show_divider_color_picker(self):
        from PyQt6.QtWidgets import QColorDialog
        if self._divider_color_dialog and self._divider_color_dialog.isVisible():
            self._divider_color_dialog.raise_()
            self._divider_color_dialog.activateWindow()
            return

        current_color = self.store.viewport.divider_line_color
        self._divider_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._divider_color_dialog.setWindowFlags(
            self._divider_color_dialog.windowFlags() | 0x00000000
        )
        self._divider_color_dialog.setModal(False)
        self._divider_color_dialog.setWindowTitle(
            self._tr("ui.choose_divider_line_color")
        )
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._divider_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                if self.main_controller:
                    if hasattr(self.main_controller, 'event_bus') and self.main_controller.event_bus:
                        self.main_controller.event_bus.emit(SettingsSetDividerLineColorEvent(color))

                if hasattr(self.main_window_app, 'ui'):

                    if hasattr(self.main_window_app.ui, 'btn_orientation'):
                        self.main_window_app.ui.btn_orientation.set_color(color)

        self._divider_color_dialog.colorSelected.connect(on_color_selected)
        self._divider_color_dialog.show()

    def show_magnifier_divider_color_picker(self):
        from PyQt6.QtWidgets import QColorDialog
        if self._magnifier_divider_color_dialog and self._magnifier_divider_color_dialog.isVisible():
            self._magnifier_divider_color_dialog.raise_()
            self._magnifier_divider_color_dialog.activateWindow()
            return

        current_color = self.store.viewport.magnifier_divider_color
        self._magnifier_divider_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._magnifier_divider_color_dialog.setWindowFlags(
            self._magnifier_divider_color_dialog.windowFlags() | 0x00000000
        )
        self._magnifier_divider_color_dialog.setModal(False)
        self._magnifier_divider_color_dialog.setWindowTitle(
            self._tr("ui.choose_magnifier_divider_line_color")
        )
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._magnifier_divider_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                if self.main_controller:
                    if hasattr(self.main_controller, 'event_bus') and self.main_controller.event_bus:
                        self.main_controller.event_bus.emit(SettingsSetMagnifierDividerColorEvent(color))

        self._magnifier_divider_color_dialog.colorSelected.connect(on_color_selected)
        self._magnifier_divider_color_dialog.show()

    def show_magnifier_border_color_picker(self):
        if self._magnifier_border_color_dialog and self._magnifier_border_color_dialog.isVisible():
            self._magnifier_border_color_dialog.raise_()
            self._magnifier_border_color_dialog.activateWindow()
            return

        current_color = self.store.viewport.magnifier_border_color
        self._magnifier_border_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._magnifier_border_color_dialog.setWindowFlags(
            self._magnifier_border_color_dialog.windowFlags() | 0x00000000
        )
        self._magnifier_border_color_dialog.setModal(False)
        self._magnifier_border_color_dialog.setWindowTitle(
            self._tr("ui.choose_magnifier_border_color")
        )
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._magnifier_border_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                if self.main_controller and self.main_controller.settings_ctrl:
                    self.main_controller.settings_ctrl.set_magnifier_border_color(color)

        self._magnifier_border_color_dialog.colorSelected.connect(on_color_selected)
        self._magnifier_border_color_dialog.show()

    def show_laser_color_picker(self):
        if self._magnifier_laser_color_dialog and self._magnifier_laser_color_dialog.isVisible():
            self._magnifier_laser_color_dialog.raise_()
            self._magnifier_laser_color_dialog.activateWindow()
            return

        current_color = self.store.viewport.magnifier_laser_color
        self._magnifier_laser_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._magnifier_laser_color_dialog.setWindowFlags(
            self._magnifier_laser_color_dialog.windowFlags() | 0x00000000
        )
        self._magnifier_laser_color_dialog.setModal(False)
        self._magnifier_laser_color_dialog.setWindowTitle(
            self._tr("ui.choose_magnifier_guides_color")
        )
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._magnifier_laser_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                if self.main_controller and self.main_controller.settings_ctrl:
                    self.main_controller.settings_ctrl.set_magnifier_laser_color(color)

        self._magnifier_laser_color_dialog.colorSelected.connect(on_color_selected)
        self._magnifier_laser_color_dialog.show()

    def show_capture_ring_color_picker(self):
        if self._capture_ring_color_dialog and self._capture_ring_color_dialog.isVisible():
            self._capture_ring_color_dialog.raise_()
            self._capture_ring_color_dialog.activateWindow()
            return

        current_color = self.store.viewport.capture_ring_color
        self._capture_ring_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._capture_ring_color_dialog.setWindowFlags(
            self._capture_ring_color_dialog.windowFlags() | 0x00000000
        )
        self._capture_ring_color_dialog.setModal(False)
        self._capture_ring_color_dialog.setWindowTitle(
            self._tr("ui.choose_capture_ring_color")
        )
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._capture_ring_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                if self.main_controller and self.main_controller.settings_ctrl:
                    self.main_controller.settings_ctrl.set_capture_ring_color(color)

        self._capture_ring_color_dialog.colorSelected.connect(on_color_selected)
        self._capture_ring_color_dialog.show()

    def apply_smart_magnifier_colors(self):
        from PyQt6.QtWidgets import QColorDialog
        current_color = self.store.viewport.magnifier_divider_color
        dialog = QColorDialog(current_color, self.main_window_app)
        dialog.setWindowTitle(self._tr("ui.choose_base_color_for_magnifier_elements"))
        self.main_window_app.theme_manager.apply_theme_to_dialog(dialog)

        def on_color_selected(color):
            if color.isValid():

                laser_color = QColor(color)
                laser_color.setAlpha(120)

                border_color = QColor(color)
                border_color.setAlpha(230)

                capture_ring_color = QColor(color)
                capture_ring_color.setAlpha(230)

                settings_ctrl = self.main_controller.settings_ctrl if self.main_controller else None

                if settings_ctrl:

                    settings_ctrl.set_magnifier_border_color(border_color)
                    settings_ctrl.set_magnifier_laser_color(laser_color)
                    settings_ctrl.set_capture_ring_color(capture_ring_color)

        dialog.colorSelected.connect(on_color_selected)
        dialog.show()

    def update_interpolation_combo_box_ui(self):
        try:
            from shared.image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False

        method_keys_all = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        method_keys = [k for k in method_keys_all if k != "EWA_LANCZOS" or WAND_AVAILABLE]

        interp_translation_map = {
            "NEAREST": "magnifier.nearest_neighbor",
            "BILINEAR": "magnifier.bilinear",
            "BICUBIC": "magnifier.bicubic",
            "LANCZOS": "magnifier.lanczos",
            "EWA_LANCZOS": "magnifier.ewa_lanczos",
        }

        target_method_key = self.store.viewport.interpolation_method
        if target_method_key not in method_keys:
            target_method_key = (
                AppConstants.DEFAULT_INTERPOLATION_METHOD
                if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys
                else (method_keys[0] if method_keys else AppConstants.DEFAULT_INTERPOLATION_METHOD)
            )
            self.store.viewport.interpolation_method = target_method_key

        try:
            current_index = method_keys.index(target_method_key)
        except ValueError:
            current_index = 0

        labels = [
            self._tr(interp_translation_map.get(key, f"magnifier.{AppConstants.INTERPOLATION_METHODS_MAP[key].lower().replace(' ', '_')}"))
            for key in method_keys
        ]
        display_text = labels[current_index] if 0 <= current_index < len(labels) else ""

        if hasattr(self.main_window_app, 'ui'):
            self.main_window_app.ui.combo_interpolation.updateState(
                count=len(method_keys),
                current_index=current_index,
                text=display_text,
                items=labels
            )

    def setup_view_buttons(self):
        lang = self.store.settings.current_language

        diff_actions = [
            (self._tr("common.switch.off"), 'off'),
            (self._tr("video.highlight"), 'highlight'),
            (self._tr("video.grayscale"), 'grayscale'),
            (self._tr("video.edge_comparison"), 'edges'),
            (self._tr("video.ssim_map"), 'ssim')
        ]
        if hasattr(self.main_window_app, 'ui'):
            self.main_window_app.ui.btn_diff_mode.set_actions(diff_actions)
            self.main_window_app.ui.btn_diff_mode.set_current_by_data(self.store.viewport.diff_mode)

        channel_actions = [
            (self._tr("video.rgb"), 'RGB'),
            (self._tr("video.red"), 'R'),
            (self._tr("video.green"), 'G'),
            (self._tr("video.blue"), 'B'),
            (self._tr("video.luminance"), 'L')
        ]
        if hasattr(self.main_window_app, 'ui'):
            self.main_window_app.ui.btn_channel_mode.set_actions(channel_actions)
            self.main_window_app.ui.btn_channel_mode.set_current_by_data(self.store.viewport.channel_view_mode)

    def _tr(self, text):
        return tr(text, self.store.settings.current_language)

    def on_language_changed(self):
        self.update_interpolation_combo_box_ui()
        self.setup_view_buttons()
