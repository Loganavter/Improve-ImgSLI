from dataclasses import replace
from typing import Any

from core.store import (
    GeometryState,
    InteractionState,
    RenderConfig,
    SessionData,
    SettingsState,
    ViewportState,
    ViewState,
)
from ui.canvas_infra.scene.registry import get_canvas_registry

from .extension_reducers import (
    reduce_render_config_extensions,
    reduce_session_data_extensions,
)
from .slot_reducers import iter_state_slot_reducers

from .actions import (
    Action,
    ClearAllCachesAction,
    InvalidateRenderCacheAction,
    SetAutoCropBlackBordersAction,
    SetChannelViewModeAction,
    SetDebugModeEnabledAction,
    SetDiffModeAction,
    SetDraggingSplitLineAction,
    SetExportFavoriteDirAction,
    SetFixedLabelDimensionsAction,
    SetImageDisplayRectAction,
    SetInteractionSessionIdAction,
    SetInteractiveModeAction,
    SetIsDraggingSliderAction,
    SetLanguageAction,
    SetLastHorizontalMovementKeyAction,
    SetLastSpacingMovementKeyAction,
    SetLastVerticalMovementKeyAction,
    SetMovementSpeedAction,
    SetPixmapDimensionsAction,
    SetPressedKeysAction,
    SetResizeInProgressAction,
    SetShowingSingleImageModeAction,
    SetShowWorkspaceTabsAction,
    SetSpaceBarPressedAction,
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    SetSystemNotificationsEnabledAction,
    SetThemeAction,
    SetUIFontFamilyAction,
    SetUIFontModeAction,
    SetUIModeAction,
    SetUserInteractingAction,
    SetVideoRecordingFpsAction,
    SetWindowGeometryAction,
    SetWindowWasMaximizedAction,
    ToggleOrientationAction,
)


def _build_viewport_state(
    state: ViewportState,
    *,
    render_config: RenderConfig | None = None,
    session_data: SessionData | None = None,
    view_state: ViewState | None = None,
    interaction_state: InteractionState | None = None,
    geometry_state: GeometryState | None = None,
) -> ViewportState:
    return ViewportState(
        render_config=render_config or state.render_config,
        session_data=session_data or state.session_data,
        view_state=view_state or state.view_state,
        interaction_state=interaction_state or state.interaction_state,
        geometry_state=geometry_state or state.geometry_state,
    )


class ViewStateReducer:
    @staticmethod
    def reduce(view_state: ViewState, action: Action, session_type: str | None = None) -> ViewState:
        if isinstance(action, SetSplitPositionAction):
            return replace(
                view_state, split_position=max(0.0, min(1.0, action.position))
            )
        if isinstance(action, SetSplitPositionVisualAction):
            return replace(
                view_state, split_position_visual=max(0.0, min(1.0, action.position))
            )
        if isinstance(action, ToggleOrientationAction):
            return replace(view_state, is_horizontal=action.is_horizontal)
        if isinstance(action, SetMovementSpeedAction):
            return replace(view_state, movement_speed_per_sec=action.speed)
        if isinstance(action, SetDiffModeAction):
            return replace(view_state, diff_mode=action.mode)
        if isinstance(action, SetChannelViewModeAction):
            return replace(view_state, channel_view_mode=action.mode)
        if isinstance(action, SetShowingSingleImageModeAction):
            return replace(view_state, showing_single_image_mode=action.mode)
        for feature in sorted(
            get_canvas_registry(session_type).get_widget_features(),
            key=lambda item: (item.reducer_order, item.name),
        ):
            reduced = feature.reduce_view_state(view_state, action)
            if reduced is not view_state:
                return reduced
        if isinstance(action, InvalidateRenderCacheAction):
            return replace(
                view_state, text_bg_visual_height=0.0, text_bg_visual_width=0.0
            )
        if isinstance(action, ClearAllCachesAction):
            return replace(
                view_state, text_bg_visual_height=0.0, text_bg_visual_width=0.0
            )
        return view_state


class InteractionStateReducer:
    @staticmethod
    def reduce(
        interaction_state: InteractionState, action: Action, session_type: str | None = None
    ) -> InteractionState:
        if isinstance(action, SetIsDraggingSliderAction):
            return replace(interaction_state, is_dragging_any_slider=action.is_dragging)
        if isinstance(action, SetResizeInProgressAction):
            return replace(interaction_state, resize_in_progress=action.enabled)
        if isinstance(action, SetInteractiveModeAction):
            return replace(interaction_state, is_interactive_mode=action.enabled)
        if isinstance(action, SetDraggingSplitLineAction):
            return replace(interaction_state, is_dragging_split_line=action.enabled)
        if isinstance(action, SetPressedKeysAction):
            return replace(interaction_state, pressed_keys=set(action.keys))
        if isinstance(action, SetSpaceBarPressedAction):
            return replace(interaction_state, space_bar_pressed=action.enabled)
        if isinstance(action, SetInteractionSessionIdAction):
            return replace(interaction_state, interaction_session_id=action.session_id)
        if isinstance(action, SetUserInteractingAction):
            return replace(interaction_state, is_user_interacting=action.enabled)
        if isinstance(action, SetLastHorizontalMovementKeyAction):
            return replace(interaction_state, last_horizontal_movement_key=action.key)
        if isinstance(action, SetLastVerticalMovementKeyAction):
            return replace(interaction_state, last_vertical_movement_key=action.key)
        if isinstance(action, SetLastSpacingMovementKeyAction):
            return replace(interaction_state, last_spacing_movement_key=action.key)
        for feature in sorted(
            get_canvas_registry(session_type).get_widget_features(),
            key=lambda item: (item.reducer_order, item.name),
        ):
            if feature.reduce_interaction_state is None:
                continue
            reduced = feature.reduce_interaction_state(interaction_state, action)
            if reduced is not interaction_state:
                return reduced
        return interaction_state


class GeometryStateReducer:
    @staticmethod
    def reduce(
        geometry_state: GeometryState, action: Action, session_type: str | None = None
    ) -> GeometryState:
        if isinstance(action, SetPixmapDimensionsAction):
            return replace(
                geometry_state, pixmap_width=action.width, pixmap_height=action.height
            )
        if isinstance(action, SetImageDisplayRectAction):
            return replace(geometry_state, image_display_rect_on_label=action.rect)
        if isinstance(action, SetFixedLabelDimensionsAction):
            return replace(
                geometry_state,
                fixed_label_width=action.width,
                fixed_label_height=action.height,
            )
        for feature in sorted(
            get_canvas_registry(session_type).get_widget_features(),
            key=lambda item: (item.reducer_order, item.name),
        ):
            if feature.reduce_geometry_state is None:
                continue
            reduced = feature.reduce_geometry_state(geometry_state, action)
            if reduced is not geometry_state:
                return reduced
        return geometry_state


class ViewportReducer:
    def __init__(self):
        self.view_state_reducer = ViewStateReducer()
        self.interaction_state_reducer = InteractionStateReducer()
        self.geometry_state_reducer = GeometryStateReducer()

    def reduce(
        self, state: ViewportState, action: Action, session_type: str | None = None
    ) -> ViewportState:
        new_view_state = self.view_state_reducer.reduce(state.view_state, action, session_type)
        new_interaction_state = self.interaction_state_reducer.reduce(
            state.interaction_state, action, session_type
        )
        new_geometry_state = self.geometry_state_reducer.reduce(
            state.geometry_state, action, session_type
        )
        new_session_data = reduce_session_data_extensions(state.session_data, action)

        if (
            new_view_state is state.view_state
            and new_interaction_state is state.interaction_state
            and new_geometry_state is state.geometry_state
            and new_session_data is state.session_data
        ):
            return state

        return _build_viewport_state(
            state,
            session_data=new_session_data,
            view_state=new_view_state,
            interaction_state=new_interaction_state,
            geometry_state=new_geometry_state,
        )


class SettingsReducer:
    @staticmethod
    def reduce(settings: SettingsState, action: Action) -> SettingsState:
        if isinstance(action, SetLanguageAction):
            return replace(settings, current_language=action.language)
        if isinstance(action, SetUIModeAction):
            return replace(settings, ui_mode=action.mode)
        if isinstance(action, SetAutoCropBlackBordersAction):
            return replace(settings, auto_crop_black_borders=action.enabled)
        if isinstance(action, SetThemeAction):
            return replace(settings, theme=action.theme)
        if isinstance(action, SetUIFontModeAction):
            return replace(settings, ui_font_mode=action.mode)
        if isinstance(action, SetUIFontFamilyAction):
            return replace(settings, ui_font_family=action.family)
        if isinstance(action, SetDebugModeEnabledAction):
            return replace(settings, debug_mode_enabled=action.enabled)
        if isinstance(action, SetSystemNotificationsEnabledAction):
            return replace(settings, system_notifications_enabled=action.enabled)
        if isinstance(action, SetVideoRecordingFpsAction):
            return replace(settings, video_recording_fps=action.fps)
        if isinstance(action, SetShowWorkspaceTabsAction):
            return replace(settings, show_workspace_tabs=action.enabled)
        if isinstance(action, SetWindowWasMaximizedAction):
            return replace(settings, window_was_maximized=action.was_maximized)
        if isinstance(action, SetWindowGeometryAction):
            return replace(
                settings,
                window_x=action.x,
                window_y=action.y,
                window_width=action.width,
                window_height=action.height,
            )
        if isinstance(action, SetExportFavoriteDirAction):
            return replace(settings, export_favorite_dir=action.path)
        return settings


class RootReducer:
    def __init__(self):
        self.viewport_reducer = ViewportReducer()
        self.settings_reducer = SettingsReducer()

    def reduce(self, store: "Store", action: Action) -> "Store":
        from core.store import Store

        active_session = store.get_active_workspace_session()
        session_type = active_session.session_type if active_session is not None else None
        new_viewport = self.viewport_reducer.reduce(store.viewport, action, session_type)
        new_render_config = reduce_render_config_extensions(
            new_viewport.render_config, action
        )
        if new_render_config is not new_viewport.render_config:
            new_viewport = _build_viewport_state(
                new_viewport, render_config=new_render_config
            )

        new_settings = self.settings_reducer.reduce(store.settings, action)

        new_slot_values: dict[str, Any] = {}
        any_slot_changed = False
        for slot_name, slot_reducer in iter_state_slot_reducers():
            current_value = store.get_session_state_slot(slot_name)
            new_value = slot_reducer(current_value, action)
            new_slot_values[slot_name] = new_value
            if new_value is not current_value:
                any_slot_changed = True

        if (
            new_viewport is store.viewport
            and not any_slot_changed
            and new_settings is store.settings
        ):
            return store

        new_store = Store()
        new_store.viewport = new_viewport
        for slot_name, new_value in new_slot_values.items():
            new_store.set_session_state_slot(slot_name, new_value, emit_scope="")
        new_store.settings = new_settings
        new_store.recorder = store.recorder
        new_store._dispatcher = store._dispatcher
        return new_store
