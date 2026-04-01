import logging

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog

from core.constants import AppConstants
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
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic import CustomGroupWidget
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

        from PyQt6.QtWidgets import QHBoxLayout

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
        defer_geometry(self)

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
            auto_calculate_psnr=self.auto_psnr_checkbox.isChecked(),
            auto_calculate_ssim=self.auto_ssim_checkbox.isChecked(),
            auto_crop_black_borders=self.crop_checkbox.isChecked(),
            ui_mode=ui_mode,
            video_recording_fps=self.spin_fps.value(),
        )

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.context.current_language = lang_code
        self.setWindowTitle(self.tr("misc.settings", self.current_language))
        self._setup_sidebar_items()

        self.ok_button.setText(self.tr("common.ok", lang_code))
        self.cancel_button.setText(self.tr("common.cancel", lang_code))

        if hasattr(self, "lang_group"):
            self.lang_group.set_title(self.tr("label.language", lang_code))
        if hasattr(self, "sys_group"):
            self.sys_group.set_title(self.tr("settings.appearance", lang_code))
        if hasattr(self, "theme_label"):
            self.theme_label.setText(self.tr("label.theme", lang_code) + ":")
        if hasattr(self, "combo_theme"):
            current_theme = self.combo_theme.currentData()
            self.combo_theme.clear()
            for key in ("auto", "light", "dark"):
                self.combo_theme.addItem(self.tr(f"settings.{key}", lang_code), key)
            idx = self.combo_theme.findData(current_theme)
            if idx != -1:
                self.combo_theme.setCurrentIndex(idx)
        if hasattr(self, "system_notifications_checkbox"):
            self.system_notifications_checkbox.setText(
                self.tr("settings.system_notifications", lang_code)
            )
        if hasattr(self, "debug_checkbox"):
            self.debug_checkbox.setText(
                self.tr("settings.enable_debug_logging", lang_code)
            )
        if hasattr(self, "ui_mode_group"):
            self.ui_mode_group.set_title(self.tr("settings.ui_mode", lang_code))
        if hasattr(self, "radio_ui_mode_beginner"):
            self.radio_ui_mode_beginner.setText(
                self.tr("settings.ui_mode_beginner", lang_code)
            )
        if hasattr(self, "radio_ui_mode_advanced"):
            self.radio_ui_mode_advanced.setText(
                self.tr("settings.ui_mode_advanced", lang_code)
            )
        if hasattr(self, "radio_ui_mode_expert"):
            self.radio_ui_mode_expert.setText(
                self.tr("settings.ui_mode_expert", lang_code)
            )
        if hasattr(self, "font_group"):
            self.font_group.set_title(self.tr("settings.ui_font", lang_code))
        if hasattr(self, "radio_font_builtin"):
            self.radio_font_builtin.setText(self.tr("settings.builtin_font", lang_code))
        if hasattr(self, "radio_font_system_default"):
            self.radio_font_system_default.setText(
                self.tr("settings.system_default", lang_code)
            )
        if hasattr(self, "radio_font_system_custom"):
            self.radio_font_system_custom.setText(self.tr("settings.custom", lang_code))
        if hasattr(self, "combo_font_family"):
            current_font = self.combo_font_family.currentData()
            from PyQt6.QtGui import QFontDatabase

            self.combo_font_family.clear()
            for fam in QFontDatabase.families():
                self.combo_font_family.addItem(fam, fam)
            idx_fam = self.combo_font_family.findData(current_font or "")
            if idx_fam != -1:
                self.combo_font_family.setCurrentIndex(idx_fam)
        if hasattr(self, "other_ui_group"):
            self.other_ui_group.set_title(
                self.tr("settings.maximum_name_length_ui", lang_code)
            )
        if hasattr(self, "res_group"):
            self.res_group.set_title(
                self.tr("settings.display_cache_resolution", lang_code)
            )
        if hasattr(self, "combo_resolution"):
            current_res = self.combo_resolution.currentData()
            mapping = {
                "Original": "settings.original",
                "8K (4320p)": "settings.resolution_8k",
                "4K (2160p)": "settings.resolution_4k",
                "2K (1440p)": "settings.resolution_2k",
                "Full HD (1080p)": "settings.resolution_full_hd",
            }
            self.combo_resolution.clear()
            for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
                self.combo_resolution.addItem(
                    self.tr(mapping.get(name_key, name_key), lang_code),
                    userData=limit,
                )
            idx_res = self.combo_resolution.findData(current_res)
            if idx_res != -1:
                self.combo_resolution.setCurrentIndex(idx_res)
        if hasattr(self, "interactive_opt_group"):
            self.interactive_opt_group.set_title(
                self.tr("settings.interactive_optimization", lang_code)
            )
        if hasattr(self, "lbl_zoom_interp"):
            self.lbl_zoom_interp.setText(
                self.tr("settings.zoom_interpolation", lang_code)
            )
        if hasattr(self, "optimize_movement_checkbox"):
            self.optimize_movement_checkbox.setText(
                self.tr("settings.optimize_magnifier_movement", lang_code)
            )
        if hasattr(self, "laser_smoothing_checkbox"):
            self.laser_smoothing_checkbox.setText(
                self.tr("settings.optimize_laser_smoothing", lang_code)
            )
        if hasattr(self, "combo_mag_interp"):
            current_mag_interp = self.combo_mag_interp.currentData()
            current_laser_interp = self.combo_laser_interp.currentData()
            current_zoom_interp = self.combo_zoom_interp.currentData()
            interp_map = {
                "NEAREST": "magnifier.nearest_neighbor",
                "BILINEAR": "magnifier.bilinear",
                "BICUBIC": "magnifier.bicubic",
                "LANCZOS": "magnifier.lanczos",
                "EWA_LANCZOS": "magnifier.ewa_lanczos",
            }
            self.combo_mag_interp.clear()
            self.combo_laser_interp.clear()
            for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
                text = self.tr(interp_map.get(key, key), lang_code)
                self.combo_mag_interp.addItem(text, key)
                self.combo_laser_interp.addItem(text, key)
            self.combo_zoom_interp.clear()
            self.combo_zoom_interp.addItem(
                self.tr(interp_map["NEAREST"], lang_code), "NEAREST"
            )
            self.combo_zoom_interp.addItem(
                self.tr(interp_map["BILINEAR"], lang_code), "BILINEAR"
            )
            for combo, value in (
                (self.combo_mag_interp, current_mag_interp),
                (self.combo_laser_interp, current_laser_interp),
                (self.combo_zoom_interp, current_zoom_interp),
            ):
                idx = combo.findData(value)
                if idx != -1:
                    combo.setCurrentIndex(idx)
        if hasattr(self, "auto_group"):
            self.auto_group.set_title(self.tr("settings.auto", lang_code))
        if hasattr(self, "crop_checkbox"):
            self.crop_checkbox.setText(
                self.tr("settings.autocrop_black_borders_on_load", lang_code)
            )
        if hasattr(self, "metrics_group"):
            self.metrics_group.set_title(self.tr("label.details", lang_code))
        if hasattr(self, "auto_psnr_checkbox"):
            self.auto_psnr_checkbox.setText(
                self.tr("settings.autocalculate_psnr", lang_code)
            )
        if hasattr(self, "auto_ssim_checkbox"):
            self.auto_ssim_checkbox.setText(
                self.tr("settings.autocalculate_ssim", lang_code)
            )
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
