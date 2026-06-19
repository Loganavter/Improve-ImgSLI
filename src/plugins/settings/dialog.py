import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog

from plugins.settings.dialog_context import SettingsDialogContext
from plugins.settings.dialog_pages import (
    init_analysis_page,
    init_general_page,
    init_interface_page,
    init_performance_page,
)
from plugins.settings.dialog_shell import (
    apply_styles,
    calculate_and_apply_geometry,
    create_scrollable_page,
    defer_geometry,
    page_scroll_area,
    setup_dialog_shell,
    setup_sidebar_items,
)
from plugins.settings.models import SettingsDialogData
from resources.translations import tr as app_tr
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import CustomGroupWidget
from ui.icon_manager import AppIcon
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class SettingsDialog(QDialog):
    def __init__(
        self,
        current_language,
        current_theme,
        current_max_length,
        min_limit,
        max_limit,
        debug_mode_enabled,
        system_notifications_enabled,
        current_resolution_limit,
        parent=None,
        tr_func=None,
        current_ui_font_mode: str = "builtin",
        current_ui_font_family: str = "",
        current_ui_mode: str = "beginner",
        optimize_magnifier_movement: bool = True,
        movement_interpolation_method: str = "BILINEAR",
        optimize_laser_smoothing: bool = False,
        interpolation_method: str = "LANCZOS",
        zoom_interpolation_method: str = "BILINEAR",
        magnifier_intersection_highlight_enabled: bool = True,
        magnifier_auto_color_new_instances: bool = True,
        auto_calculate_psnr: bool = False,
        auto_calculate_ssim: bool = False,
        auto_crop_black_borders: bool = True,
        current_video_fps: int = 60,
        store=None,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("SettingsDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language
        self.theme_manager = ThemeManager.get_instance()
        self.context = SettingsDialogContext(
            current_language=current_language,
            current_theme=current_theme,
            current_max_length=current_max_length,
            min_limit=min_limit,
            max_limit=max_limit,
            debug_mode_enabled=debug_mode_enabled,
            system_notifications_enabled=system_notifications_enabled,
            current_resolution_limit=current_resolution_limit,
            tr_func=self.tr,
            current_ui_font_mode=current_ui_font_mode,
            current_ui_font_family=current_ui_font_family,
            current_ui_mode=current_ui_mode,
            optimize_magnifier_movement=optimize_magnifier_movement,
            movement_interpolation_method=movement_interpolation_method,
            optimize_laser_smoothing=optimize_laser_smoothing,
            interpolation_method=interpolation_method,
            zoom_interpolation_method=zoom_interpolation_method,
            magnifier_intersection_highlight_enabled=magnifier_intersection_highlight_enabled,
            magnifier_auto_color_new_instances=magnifier_auto_color_new_instances,
            auto_calculate_psnr=auto_calculate_psnr,
            auto_calculate_ssim=auto_calculate_ssim,
            auto_crop_black_borders=auto_crop_black_borders,
            current_video_fps=current_video_fps,
            store=store,
        )
        self._custom_group_widget_cls = CustomGroupWidget

        self.setWindowTitle(self.tr("misc.settings", self.current_language))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        from PySide6.QtWidgets import QHBoxLayout

        self.main_layout = QHBoxLayout(self)
        setup_dialog_shell(self)
        init_general_page(self, self.context)
        init_interface_page(self, self.context)
        init_performance_page(self, self.context)
        init_analysis_page(self, self.context)
        self._setup_sidebar_items()
        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)
        self.sidebar.setCurrentRow(0)
        calculate_and_apply_geometry(self)

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.ApplicationFontChange:
            defer_geometry(self)
        super().changeEvent(event)

    def _calculate_and_apply_geometry(self):
        calculate_and_apply_geometry(self)

    def _setup_sidebar_items(self):
        setup_sidebar_items(self)

    def _update_sidebar_icons(self):
        self.sidebar.refresh_icons()

    def _create_scrollable_page(self):
        return create_scrollable_page()

    def _page_scroll_area(self, page):
        return page_scroll_area(page)

    def _init_general_page(self):
        init_general_page(self, self.context)

    def _init_interface_page(self):
        init_interface_page(self, self.context)

    def _init_performance_page(self):
        init_performance_page(self, self.context)

    def _init_analysis_page(self):
        init_analysis_page(self, self.context)

    def _on_category_changed(self, row):
        self.pages_stack.setCurrentIndex(row)
        self._update_sidebar_icons()

    def _apply_styles(self):
        apply_styles(self)

    def get_settings(self):
        selected_language = next(
            (
                lang
                for radio, lang in {
                    self.radio_en: "en",
                    self.radio_ru: "ru",
                    self.radio_zh: "zh",
                    self.radio_pt_br: "pt_BR",
                }.items()
                if radio.isChecked()
            ),
            "en",
        )
        ui_font_mode = next(
            (
                mode
                for radio, mode in {
                    self.radio_font_system_default: "system_default",
                    self.radio_font_system_custom: "system_custom",
                }.items()
                if radio.isChecked()
            ),
            "builtin",
        )
        ui_mode = next(
            (
                mode
                for radio, mode in {
                    self.radio_ui_mode_expert: "expert",
                    self.radio_ui_mode_advanced: "advanced",
                }.items()
                if radio.isChecked()
            ),
            "beginner",
        )

        return SettingsDialogData(
            language=selected_language,
            theme=self.combo_theme.currentData(),
            max_name_length=self.spin_max_length.value(),
            debug_enabled=self.debug_checkbox.isChecked(),
            system_notifications_enabled=self.system_notifications_checkbox.isChecked(),
            resolution_limit=self.combo_resolution.currentData(),
            ui_font_mode=ui_font_mode,
            ui_font_family=self.combo_font_family.currentData() or "",
            optimize_magnifier_movement=self.optimize_movement_checkbox.isChecked(),
            magnifier_interpolation_method=self.combo_mag_interp.currentData()
            or "BILINEAR",
            optimize_laser_smoothing=self.laser_smoothing_checkbox.isChecked(),
            laser_interpolation_method=self.combo_laser_interp.currentData()
            or "BILINEAR",
            zoom_interpolation_method=self.combo_zoom_interp.currentData()
            or "BILINEAR",
            magnifier_intersection_highlight_enabled=self.magnifier_intersection_highlight_checkbox.isChecked(),
            magnifier_auto_color_new_instances=self.magnifier_auto_color_checkbox.isChecked(),
            auto_calculate_psnr=self.auto_psnr_checkbox.isChecked(),
            auto_calculate_ssim=self.auto_ssim_checkbox.isChecked(),
            auto_crop_black_borders=self.crop_checkbox.isChecked(),
            ui_mode=ui_mode,
            video_recording_fps=self.spin_fps.value(),
            show_workspace_tabs=self.show_workspace_tabs_checkbox.isChecked(),
        )

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.context.current_language = lang_code
        if not hasattr(self, "_translations_binder"):
            from plugins.settings.translations import build_translations_binder
            self._translations_binder = build_translations_binder(self)
        self._translations_binder.apply(lang_code)
        self._setup_sidebar_items()
        curr = self.sidebar.currentRow()
        self.sidebar.setCurrentRow(-1)
        self.sidebar.setCurrentRow(curr)

    def accept(self):
        self._reset_button_states()
        super().accept()

    def reject(self):
        self._reset_button_states()
        super().reject()

    def _reset_button_states(self):
        if hasattr(self, "ok_button"):
            self.ok_button.setProperty("state", "normal")
            self.ok_button.update()
        if hasattr(self, "cancel_button"):
            self.cancel_button.setProperty("state", "normal")
            self.cancel_button.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clear_input_focus()
        super().mousePressEvent(event)

    def clear_input_focus(self):
        focused_widget = self.focusWidget()
        if focused_widget and hasattr(focused_widget, "clearFocus"):
            focused_widget.clearFocus()
