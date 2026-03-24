import logging

from PyQt6.QtCore import Qt

from core.constants import AppConstants
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class DialogManager:
    def __init__(self, host):
        self.host = host

    def show_help_dialog(self):
        if (
            self.host.main_controller is None
            or self.host.main_controller.plugin_coordinator is None
        ):
            logger.warning("UIManager.show_help_dialog: plugin coordinator is unavailable")
            return

        try:
            self.host.main_controller.plugin_coordinator.execute_command(
                "help",
                "show_dialog",
                parent=self.host.parent_widget,
                language=self.host.store.settings.current_language,
            )
        except Exception as e:
            logger.error("UIManager.show_help_dialog failed: %s", e)

    def show_settings_dialog(self):
        from plugins.settings.application_service import SettingsApplicationService
        from plugins.settings.dialog import SettingsDialog

        logger.debug(
            "UIManager.show_settings_dialog existing=%s zoom_interp=%s main_interp=%s optimize_mag=%s optimize_laser=%s",
            self.host._settings_dialog is not None,
            getattr(
                self.host.store.viewport.render_config,
                "zoom_interpolation_method",
                None,
            ),
            getattr(self.host.store.viewport, "interpolation_method", None),
            getattr(self.host.store.viewport, "optimize_magnifier_movement", None),
            getattr(self.host.store.viewport, "optimize_laser_smoothing", None),
        )

        if self.host._settings_dialog is None:
            if self.host._settings_application_service is None:
                self.host._settings_application_service = SettingsApplicationService(
                    self.host.store,
                    self.host.main_controller,
                    self.host.event_bus,
                    self.host,
                )
            self.host._settings_dialog = SettingsDialog(
                current_language=self.host.store.settings.current_language,
                current_theme=self.host.store.settings.theme,
                current_max_length=self.host.store.viewport.max_name_length,
                min_limit=AppConstants.MIN_NAME_LENGTH_LIMIT,
                max_limit=AppConstants.MAX_NAME_LENGTH_LIMIT,
                debug_mode_enabled=self.host.store.settings.debug_mode_enabled,
                system_notifications_enabled=getattr(
                    self.host.store.settings, "system_notifications_enabled", True
                ),
                current_resolution_limit=self.host.store.viewport.display_resolution_limit,
                parent=self.host.parent_widget,
                tr_func=tr,
                current_ui_font_mode=getattr(
                    self.host.store.settings, "ui_font_mode", "builtin"
                ),
                current_ui_font_family=getattr(
                    self.host.store.settings, "ui_font_family", ""
                ),
                current_ui_mode=getattr(
                    self.host.store.settings, "ui_mode", "beginner"
                ),
                optimize_magnifier_movement=self.host.store.viewport.optimize_magnifier_movement,
                movement_interpolation_method=self.host.store.viewport.render_config.magnifier_movement_interpolation_method,
                optimize_laser_smoothing=self.host.store.viewport.optimize_laser_smoothing,
                interpolation_method=self.host.store.viewport.interpolation_method,
                zoom_interpolation_method=self.host.store.viewport.render_config.zoom_interpolation_method,
                auto_calculate_psnr=self.host.store.viewport.auto_calculate_psnr,
                auto_calculate_ssim=self.host.store.viewport.auto_calculate_ssim,
                auto_crop_black_borders=getattr(
                    self.host.store.settings, "auto_crop_black_borders", True
                ),
                current_video_fps=getattr(
                    self.host.store.settings, "video_recording_fps", 60
                ),
                store=self.host.store,
            )
            self.host._settings_dialog.setAttribute(
                Qt.WidgetAttribute.WA_DeleteOnClose, True
            )
            logger.debug(
                "UIManager.show_settings_dialog created dialog zoom_interp=%s",
                getattr(
                    self.host.store.viewport.render_config,
                    "zoom_interpolation_method",
                    None,
                ),
            )

            self.host._settings_dialog.accepted.connect(
                lambda: self.host._settings_application_service.apply(
                    self.host._settings_dialog.get_settings()
                )
            )
            self.host._settings_dialog.destroyed.connect(
                lambda: setattr(self.host, "_settings_dialog", None)
            )

        if self.host._settings_dialog is not None:
            logger.debug(
                "UIManager.show_settings_dialog showing dialog object=%s visible=%s",
                hex(id(self.host._settings_dialog)),
                self.host._settings_dialog.isVisible(),
            )
            self.host._settings_dialog.show()
            self.host._settings_dialog.raise_()
            self.host._settings_dialog.activateWindow()

    def show_export_dialog(
        self,
        dialog_state,
        preview_image: object | None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
    ):
        from plugins.export.dialog import ExportDialog

        dialog = ExportDialog(
            dialog_state=dialog_state,
            parent=None,
            tr_func=tr,
            preview_image=preview_image,
            suggested_filename=suggested_filename,
            on_set_favorite_dir=on_set_favorite_dir,
        )
        return dialog.exec(), dialog.get_export_options()
