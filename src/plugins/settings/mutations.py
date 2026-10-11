from __future__ import annotations

from core.state_management.actions import (
    InvalidateRenderCacheAction,
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetIncludeFileNamesInSavedAction,
    SetLanguageAction,
    SetMaxNameLengthAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
    SetUIModeAction,
)
from domain.qt_adapters import color_to_hex
from ui.canvas_infra.scene.property_access import (
    deserialize_canvas_feature_setting,
    get_canvas_feature_property_by_setting_key,
    read_canvas_feature_property,
    serialize_canvas_feature_setting,
    write_canvas_feature_property,
)

VIEWPORT_GETTERS = {
    "include_file_names_in_saved": lambda store: store.viewport.render_config.include_file_names_in_saved,
    "font_size_percent": lambda store: store.viewport.render_config.font_size_percent,
    "font_weight": lambda store: store.viewport.render_config.font_weight,
    "file_name_color": lambda store: store.viewport.render_config.file_name_color,
    "file_name_bg_color": lambda store: store.viewport.render_config.file_name_bg_color,
    "draw_text_background": lambda store: store.viewport.render_config.draw_text_background,
    "text_placement_mode": lambda store: store.viewport.render_config.text_placement_mode,
    "text_alpha_percent": lambda store: store.viewport.render_config.text_alpha_percent,
    "max_name_length": lambda store: store.viewport.render_config.max_name_length,
}

VIEWPORT_ACTIONS = {
    "include_file_names_in_saved": SetIncludeFileNamesInSavedAction,
    "font_size_percent": SetFontSizePercentAction,
    "font_weight": SetFontWeightAction,
    "file_name_color": SetFileNameColorAction,
    "file_name_bg_color": SetFileNameBgColorAction,
    "draw_text_background": SetDrawTextBackgroundAction,
    "text_placement_mode": SetTextPlacementModeAction,
    "text_alpha_percent": SetTextAlphaPercentAction,
    "max_name_length": SetMaxNameLengthAction,
}

#: Store-settings attribute -> (action class, payload field). Every settings
#: write goes through the Dispatcher via one of these actions — a direct
#: ``store.settings.<attr> = value`` bypass is forbidden (contract dogma:
#: test_no_direct_settings_mutation). An unmapped attribute is a fail-loud
#: ValueError, never a silent setattr.
SETTINGS_ACTIONS = {
    "current_language": (SetLanguageAction, "language"),
    "ui_mode": (SetUIModeAction, "mode"),
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

        try:
            action_cls, field_name = SETTINGS_ACTIONS[attr]
        except KeyError:
            raise ValueError(
                f"No dispatch action mapped for settings attribute {attr!r}; "
                "add it to SETTINGS_ACTIONS instead of setattr "
                f"({type(self).__name__}.set_settings_value)"
            ) from None
        dispatcher = self.store.get_dispatcher()
        dispatcher.dispatch(action_cls(**{field_name: value}))
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

    def set_canvas_feature_setting(
        self,
        setting_key: str,
        raw_value,
        *,
        invalidate_render_cache: bool = False,
        emit_scope: str | None = None,
        request_core_update: bool = False,
    ) -> bool:
        session = self.store.get_active_workspace_session()
        if session is None:
            # Clean error, never an assert: canvas feature keys are resolved
            # per session_type, and without an active session there is
            # nothing to resolve against.
            raise RuntimeError(
                f"Cannot apply canvas feature setting {setting_key!r} "
                "with no active workspace session"
            )
        session_type = session.session_type
        prop = get_canvas_feature_property_by_setting_key(session_type, setting_key)
        if prop is None:
            raise KeyError(f"Unknown canvas feature setting key: {setting_key}")

        current_channels = read_canvas_feature_property(self.store.viewport, prop)
        next_channels = deserialize_canvas_feature_setting(prop, raw_value)
        if current_channels == next_channels:
            return False

        # Generic property path: no per-feature Redux action exists here and
        # this layer must not import tab internals, so the write stays on
        # the property writer. Tab-owned widgets dispatch their own
        # undoable actions through tab reducers; this path announces the
        # tweak through the Dispatcher (traced) and persists + emits.
        write_canvas_feature_property(self.store.viewport, prop, next_channels)
        self.settings_manager._save_setting(
            setting_key,
            serialize_canvas_feature_setting(prop, next_channels),
        )
        if invalidate_render_cache:
            self.store.get_dispatcher().dispatch(
                InvalidateRenderCacheAction(), scope="viewport"
            )
        self.notifier.emit_state_change(emit_scope)
        if request_core_update:
            self.notifier.request_core_update()
        return True

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
        # Coalesce the per-setter emit_state_change calls into ONE flush: each
        # setter emitted its own state change, so the (non-trivial) chrome-sync
        # handler ran 2x per slider tick. ``batch_changes`` defers every emit to
        # a single flush at block exit (invalidate first, so subscribers see the
        # invalidated cache).
        with self.store.batch_changes():
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

            # Canonical UI range is 5..100 (font flyout opacity slider); keep the
            # stored value inside it so save -> load is a fixpoint (the feature
            # property path clamps to the same range).
            normalized_alpha = max(5, min(100, int(text_alpha_percent)))
            changed |= self.set_viewport_value(
                "text_alpha_percent",
                normalized_alpha,
                setting_key="text_alpha_percent",
            )

            if changed:
                self.notifier.invalidate_render_cache()

        return changed