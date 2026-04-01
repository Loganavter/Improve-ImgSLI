from __future__ import annotations

from core.state_management.actions import (
    InvalidateRenderCacheAction,
    SetCaptureRingColorAction,
    SetDividerLineColorAction,
    SetDividerLineThicknessAction,
    SetDividerLineVisibleAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetIncludeFileNamesInSavedAction,
    SetMagnifierBorderColorAction,
    SetMagnifierDividerColorAction,
    SetMagnifierDividerThicknessAction,
    SetMagnifierDividerVisibleAction,
    SetMagnifierLaserColorAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
)
from domain.qt_adapters import color_to_hex

VIEWPORT_GETTERS = {
    "include_file_names_in_saved": lambda store: store.viewport.render_config.include_file_names_in_saved,
    "divider_line_visible": lambda store: store.viewport.render_config.divider_line_visible,
    "divider_line_color": lambda store: store.viewport.render_config.divider_line_color,
    "divider_line_thickness": lambda store: store.viewport.render_config.divider_line_thickness,
    "magnifier_divider_visible": lambda store: store.viewport.render_config.magnifier_divider_visible,
    "magnifier_divider_color": lambda store: store.viewport.render_config.magnifier_divider_color,
    "magnifier_divider_thickness": lambda store: store.viewport.render_config.magnifier_divider_thickness,
    "magnifier_border_color": lambda store: store.viewport.render_config.magnifier_border_color,
    "magnifier_laser_color": lambda store: store.viewport.render_config.magnifier_laser_color,
    "capture_ring_color": lambda store: store.viewport.render_config.capture_ring_color,
    "font_size_percent": lambda store: store.viewport.render_config.font_size_percent,
    "font_weight": lambda store: store.viewport.render_config.font_weight,
    "file_name_color": lambda store: store.viewport.render_config.file_name_color,
    "file_name_bg_color": lambda store: store.viewport.render_config.file_name_bg_color,
    "draw_text_background": lambda store: store.viewport.render_config.draw_text_background,
    "text_placement_mode": lambda store: store.viewport.render_config.text_placement_mode,
    "text_alpha_percent": lambda store: store.viewport.render_config.text_alpha_percent,
}

VIEWPORT_ACTIONS = {
    "include_file_names_in_saved": SetIncludeFileNamesInSavedAction,
    "divider_line_visible": SetDividerLineVisibleAction,
    "divider_line_color": SetDividerLineColorAction,
    "divider_line_thickness": SetDividerLineThicknessAction,
    "magnifier_divider_visible": SetMagnifierDividerVisibleAction,
    "magnifier_divider_color": SetMagnifierDividerColorAction,
    "magnifier_divider_thickness": SetMagnifierDividerThicknessAction,
    "magnifier_border_color": SetMagnifierBorderColorAction,
    "magnifier_laser_color": SetMagnifierLaserColorAction,
    "capture_ring_color": SetCaptureRingColorAction,
    "font_size_percent": SetFontSizePercentAction,
    "font_weight": SetFontWeightAction,
    "file_name_color": SetFileNameColorAction,
    "file_name_bg_color": SetFileNameBgColorAction,
    "draw_text_background": SetDrawTextBackgroundAction,
    "text_placement_mode": SetTextPlacementModeAction,
    "text_alpha_percent": SetTextAlphaPercentAction,
}

class SettingsMutationService:
    def __init__(self, store, settings_manager, notifier):
        self.store = store
        self.settings_manager = settings_manager
        self.notifier = notifier

    def set_viewport_value(
        self,
        attr: str,
        value,
        *,
        setting_key: str | None = None,
        persist_value=None,
        invalidate_render_cache: bool = False,
        emit_scope: str | None = None,
        request_core_update: bool = False,
    ) -> bool:
        current_value = VIEWPORT_GETTERS[attr](self.store)
        if current_value == value:
            return False

        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(VIEWPORT_ACTIONS[attr](value), scope="viewport")
        if invalidate_render_cache:
            dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        if setting_key is not None:
            persisted = value if persist_value is None else persist_value
            self.settings_manager._save_setting(setting_key, persisted)
        self.notifier.emit_state_change(emit_scope)
        if request_core_update:
            self.notifier.request_core_update()
        return True

    def set_settings_value(
        self,
        attr: str,
        value,
        *,
        setting_key: str | None = None,
        emit_scope: str | None = "settings",
        request_core_update: bool = False,
    ) -> bool:
        if getattr(self.store.settings, attr) == value:
            return False

        setattr(self.store.settings, attr, value)
        if setting_key is not None:
            self.settings_manager._save_setting(setting_key, value)
        self.notifier.emit_state_change(emit_scope)
        if request_core_update:
            self.notifier.request_core_update()
        return True

    def set_viewport_color(
        self,
        attr: str,
        color,
        *,
        setting_key: str,
        invalidate_render_cache: bool = False,
        emit_scope: str | None = None,
        request_core_update: bool = False,
    ) -> bool:
        return self.set_viewport_value(
            attr,
            color,
            setting_key=setting_key,
            persist_value=color_to_hex(color),
            invalidate_render_cache=invalidate_render_cache,
            emit_scope=emit_scope,
            request_core_update=request_core_update,
        )

    def apply_font_settings(
        self,
        *,
        size: int,
        font_weight: int,
        color,
        bg_color,
        draw_background: bool,
        placement_mode: str,
        text_alpha_percent: int,
    ) -> bool:
        changed = False
        changed |= self.set_viewport_value(
            "font_size_percent",
            size,
            setting_key="font_size_percent",
        )
        changed |= self.set_viewport_value(
            "font_weight",
            font_weight,
            setting_key="font_weight",
        )
        changed |= self.set_viewport_color(
            "file_name_color",
            color,
            setting_key="filename_color",
        )
        changed |= self.set_viewport_color(
            "file_name_bg_color",
            bg_color,
            setting_key="filename_bg_color",
        )
        changed |= self.set_viewport_value(
            "draw_text_background",
            draw_background,
            setting_key="draw_text_background",
        )
        changed |= self.set_viewport_value(
            "text_placement_mode",
            placement_mode,
            setting_key="text_placement_mode",
        )

        normalized_alpha = max(0, min(100, int(text_alpha_percent)))
        changed |= self.set_viewport_value(
            "text_alpha_percent",
            normalized_alpha,
            setting_key="text_alpha_percent",
        )

        if changed:
            self.notifier.invalidate_render_cache()
            self.notifier.emit_state_change()
        return changed
