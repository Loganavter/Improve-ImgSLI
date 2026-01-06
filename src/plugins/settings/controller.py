from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog
from core.events import (
    CoreUpdateRequestedEvent,
    SettingsChangeLanguageEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    SettingsApplyFontSettingsEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsSetDividerLineColorEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    SettingsSetMagnifierDividerColorEvent,
    SettingsToggleAutoCropBlackBordersEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerThicknessEvent,
)
import logging

logger = logging.getLogger("ImproveImgSLI")

class SettingsController(QObject):

    update_requested = pyqtSignal()

    def __init__(self, store, settings_manager, presenter=None, event_bus=None):
        super().__init__()
        self.store = store
        self.settings_manager = settings_manager
        self.presenter = presenter
        self.event_bus = event_bus

    def change_language(self, lang_code: str):
        self.store.settings.current_language = lang_code
        self.store.emit_state_change("settings")
        if self.presenter:
            self.presenter.on_language_changed()
        self.settings_manager._save_setting("language", lang_code)

    def toggle_include_filenames_in_saved(self, checked: bool):
        self.store.viewport.include_file_names_in_saved = checked

        self.store.invalidate_render_cache()
        self.store.emit_state_change()
        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            self.update_requested.emit()

    def apply_font_settings(self, size: int, font_weight: int, color: QColor, bg_color: QColor, draw_background: bool, placement_mode: str, text_alpha_percent: int):
        changed = False
        if self.store.viewport.font_size_percent != size:
            self.store.viewport.font_size_percent = size
            self.settings_manager._save_setting("font_size_percent", size)
            changed = True
        if self.store.viewport.font_weight != font_weight:
            self.store.viewport.font_weight = font_weight
            self.settings_manager._save_setting("font_weight", font_weight)
            changed = True
        if self.store.viewport.file_name_color != color:
            self.store.viewport.file_name_color = color
            self.settings_manager._save_setting("filename_color", color.name(QColor.NameFormat.HexArgb))
            changed = True
        if self.store.viewport.file_name_bg_color != bg_color:
            self.store.viewport.file_name_bg_color = bg_color
            self.settings_manager._save_setting("filename_bg_color", bg_color.name(QColor.NameFormat.HexArgb))
            changed = True
        if self.store.viewport.draw_text_background != draw_background:
            self.store.viewport.draw_text_background = draw_background
            self.settings_manager._save_setting("draw_text_background", draw_background)
            changed = True
        if self.store.viewport.text_placement_mode != placement_mode:
            self.store.viewport.text_placement_mode = placement_mode
            self.settings_manager._save_setting("text_placement_mode", placement_mode)
            changed = True
        text_alpha_percent = max(0, min(100, int(text_alpha_percent)))
        if getattr(self.store.viewport, "text_alpha_percent", 100) != text_alpha_percent:
            self.store.viewport.text_alpha_percent = text_alpha_percent
            self.settings_manager._save_setting("text_alpha_percent", text_alpha_percent)
            changed = True
        if changed:

            self.store.invalidate_render_cache()
            self.store.emit_state_change()

    def toggle_divider_line_visibility(self, checked: bool):
        is_visible = not checked
        if self.store.viewport.divider_line_visible != is_visible:
            self.store.viewport.divider_line_visible = is_visible
            self.settings_manager._save_setting("divider_line_visible", is_visible)
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_divider_line_color(self, color: QColor):
        if self.store.viewport.divider_line_color != color:
            self.store.viewport.divider_line_color = color
            self.settings_manager._save_setting("divider_line_color", color.name(QColor.NameFormat.HexArgb))
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_divider_line_thickness(self, thickness: int):
        thickness = max(0, min(20, int(thickness)))

        if getattr(self.store.viewport, 'divider_line_thickness', -1) != thickness:
            self.store.viewport.divider_line_thickness = thickness

            self.store.invalidate_render_cache()
            self.settings_manager._save_setting("divider_line_thickness", thickness)
            self.store.emit_state_change()

            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def toggle_magnifier_divider_visibility(self, visible: bool):
        is_visible = not visible
        if self.store.viewport.magnifier_divider_visible != is_visible:
            self.store.viewport.magnifier_divider_visible = is_visible
            self.settings_manager._save_setting("magnifier_divider_visible", is_visible)
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_magnifier_divider_color(self, color: QColor):
        if self.store.viewport.magnifier_divider_color != color:
            self.store.viewport.magnifier_divider_color = color
            self.settings_manager._save_setting("magnifier_divider_color", color.name(QColor.NameFormat.HexArgb))
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def show_magnifier_divider_color_picker(self):
        dialog = QColorDialog(self.store.viewport.magnifier_divider_color, self.presenter.main_window_app if self.presenter else None)
        if dialog.exec():
            self.set_magnifier_divider_color(dialog.selectedColor())
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_magnifier_divider_thickness(self, thickness: int):
        thickness = max(0, min(10, int(thickness)))

        current_thickness = getattr(self.store.viewport, 'magnifier_divider_thickness', -1)

        if current_thickness != thickness:
            self.store.viewport.magnifier_divider_thickness = thickness

            self.store.invalidate_render_cache()

            self.settings_manager._save_setting("magnifier_divider_thickness", thickness)

            self.store.emit_state_change()

            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def toggle_auto_crop_black_borders(self, enabled: bool):
        if self.store.settings.auto_crop_black_borders != enabled:
            self.store.settings.auto_crop_black_borders = enabled
            self.settings_manager._save_setting("auto_crop_black_borders", enabled)
            self.store.emit_state_change("settings")

    def apply_smart_magnifier_colors(self):
        dialog = QColorDialog(self.store.viewport.magnifier_divider_color, self.presenter.main_window_app if self.presenter else None)
        if dialog.exec():
            base_color = dialog.selectedColor()
            self.set_magnifier_divider_color(base_color)
            laser_color = QColor(base_color)
            laser_color.setAlpha(120)
            self.set_magnifier_laser_color(laser_color)
            capture_ring_color = QColor(base_color)
            capture_ring_color.setAlpha(230)
            self.set_capture_ring_color(capture_ring_color)

            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_magnifier_border_color(self, color: QColor):
        if self.store.viewport.magnifier_border_color != color:
            self.store.viewport.magnifier_border_color = color
            self.settings_manager._save_setting("magnifier_border_color", color.name(QColor.NameFormat.HexArgb))

            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_magnifier_laser_color(self, color: QColor):
        if self.store.viewport.magnifier_laser_color != color:
            self.store.viewport.magnifier_laser_color = color
            self.settings_manager._save_setting("magnifier_laser_color", color.name(QColor.NameFormat.HexArgb))

            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_capture_ring_color(self, color: QColor):
        if self.store.viewport.capture_ring_color != color:
            self.store.viewport.capture_ring_color = color
            self.settings_manager._save_setting("capture_ring_color", color.name(QColor.NameFormat.HexArgb))

            self.store.invalidate_render_cache()
            self.store.emit_state_change()
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def set_ui_mode(self, mode: str):

        if mode == "advanced":

            saved_mode = self.settings_manager._load_setting("ui_mode", "beginner")
            if saved_mode == "expert":
                mode = "expert"

        if mode not in ("beginner", "advanced", "expert", "minimal"):
            logger.warning(f"Invalid UI mode: {mode}, using 'beginner'")
            mode = "beginner"

        if getattr(self.store.settings, "ui_mode", "beginner") != mode:
            self.store.settings.ui_mode = mode
            self.settings_manager._save_setting("ui_mode", mode)
            self.store.emit_state_change("settings")

            if self.event_bus:
                from core.events import SettingsUIModeChangedEvent
                self.event_bus.emit(SettingsUIModeChangedEvent(mode))

    def on_change_language(self, event: SettingsChangeLanguageEvent):
        self.change_language(event.lang_code)

    def on_toggle_include_filenames_in_saved(self, event: SettingsToggleIncludeFilenamesInSavedEvent):
        self.toggle_include_filenames_in_saved(event.include)

    def on_apply_font_settings(self, event: SettingsApplyFontSettingsEvent):
        self.apply_font_settings(event.size, event.weight, event.color, event.bg_color, event.draw_bg, event.placement, event.alpha)

    def on_toggle_divider_line_visibility(self, event: SettingsToggleDividerLineVisibilityEvent):
        self.toggle_divider_line_visibility(not event.visible)

    def on_set_divider_line_color(self, event: SettingsSetDividerLineColorEvent):
        self.set_divider_line_color(event.color)

    def on_toggle_magnifier_divider_visibility(self, event: SettingsToggleMagnifierDividerVisibilityEvent):
        self.toggle_magnifier_divider_visibility(not event.visible)

    def on_set_magnifier_divider_color(self, event: SettingsSetMagnifierDividerColorEvent):
        self.set_magnifier_divider_color(event.color)

    def on_toggle_auto_crop_black_borders(self, event: SettingsToggleAutoCropBlackBordersEvent):
        self.toggle_auto_crop_black_borders(event.enabled)

    def on_set_divider_line_thickness(self, event: SettingsSetDividerLineThicknessEvent):
        self.set_divider_line_thickness(event.thickness)

    def on_set_magnifier_divider_thickness(self, event: SettingsSetMagnifierDividerThicknessEvent):
        self.set_magnifier_divider_thickness(event.thickness)

