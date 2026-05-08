from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.events import ViewportToggleOrientationEvent
from core.state_management.action_base import Action
from core.state_management.viewport_actions import (
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    ToggleOrientationAction,
)
from core.store_viewport import RenderConfig, ViewState
from domain.qt_adapters import color_to_qcolor
from domain.qt_adapters import qcolor_to_color
from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor, TrackDescriptor

from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)

from .actions import (
    SetDividerColorAction,
    SetDividerThicknessAction,
    SetDividerVisibleAction,
)
from .events import (
    SettingsSetDividerColorEvent,
    SettingsSetDividerThicknessEvent,
    SettingsToggleDividerVisibilityEvent,
)
from .state import DividerWidgetState, get_divider_widget_state, replace_divider_widget_state

def reduce_divider_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetSplitPositionAction):
        return replace(view_state, split_position=max(0.0, min(1.0, action.position)))
    if isinstance(action, SetSplitPositionVisualAction):
        return replace(view_state, split_position_visual=max(0.0, min(1.0, action.position)))
    if isinstance(action, ToggleOrientationAction):
        return replace(view_state, is_horizontal=action.is_horizontal)
    if isinstance(action, SetDividerVisibleAction):
        state = get_divider_widget_state(view_state).clone()
        state.visible = bool(action.visible)
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerColorAction):
        state = get_divider_widget_state(view_state).clone()
        state.color = action.color
        return replace_divider_widget_state(view_state, state)
    if isinstance(action, SetDividerThicknessAction):
        state = get_divider_widget_state(view_state).clone()
        state.thickness = max(0, int(action.thickness))
        return replace_divider_widget_state(view_state, state)
    return view_state

def reduce_divider_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    return config

def _set_snapshot_divider_state(snap, state: DividerWidgetState) -> None:
    view_state = snap.viewport_state.view_state
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["divider"] = state
    view_state.canvas_widget_state = canvas_widget_state

def _track_descriptor(track_id: str, label: str, kind: str) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
        "color": (
            ChannelDescriptor("r", "R", "color"),
            ChannelDescriptor("g", "G", "color"),
            ChannelDescriptor("b", "B", "color"),
            ChannelDescriptor("a", "A", "color"),
        ),
    }
    return TrackDescriptor(id=track_id, label=label, kind=kind, channels=defaults[kind])

def build_divider_properties() -> tuple[CanvasFeatureProperty, ...]:
    position = _track_descriptor("splitter.main.position", "Position", "scalar")
    orientation = _track_descriptor("splitter.main.orientation", "Orientation", "bool")
    color = _track_descriptor("splitter.main.color", "Color", "color")
    visible = _track_descriptor("splitter.main.visible", "Visible", "bool")
    thickness = _track_descriptor("splitter.main.thickness", "Thickness", "scalar")
    return (
        CanvasFeatureProperty(
            id=position.id,
            label=position.label,
            kind=position.kind,
            channels=position.channels,
            group_id="divider",
            group_label="Divider",
            read_snapshot=lambda snap: {"value": float(snap.viewport_state.view_state.split_position)},
            write_snapshot=lambda snap, ch: (
                setattr(snap.viewport_state.view_state, "split_position", float(ch["value"])),
                setattr(snap.viewport_state.view_state, "split_position_visual", float(ch["value"])),
            ),
            order=10,
        ),
        CanvasFeatureProperty(
            id=orientation.id,
            label=orientation.label,
            kind=orientation.kind,
            channels=orientation.channels,
            group_id="divider",
            group_label="Divider",
            read_snapshot=lambda snap: {"value": bool(snap.viewport_state.view_state.is_horizontal)},
            write_snapshot=lambda snap, ch: setattr(snap.viewport_state.view_state, "is_horizontal", bool(ch["value"])),
            order=11,
        ),
        CanvasFeatureProperty(
            id=color.id,
            label=color.label,
            kind=color.kind,
            channels=color.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.color",
            read_snapshot=lambda snap: {
                "r": int(get_divider_widget_state(snap.viewport_state.view_state).color.r),
                "g": int(get_divider_widget_state(snap.viewport_state.view_state).color.g),
                "b": int(get_divider_widget_state(snap.viewport_state.view_state).color.b),
                "a": int(get_divider_widget_state(snap.viewport_state.view_state).color.a),
            },
            write_snapshot=lambda snap, ch: _set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    color=Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
                ),
            ),
            order=12,
        ),
        CanvasFeatureProperty(
            id=visible.id,
            label=visible.label,
            kind=visible.kind,
            channels=visible.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.visible",
            read_snapshot=lambda snap: {"value": bool(get_divider_widget_state(snap.viewport_state.view_state).visible)},
            write_snapshot=lambda snap, ch: _set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    visible=bool(ch["value"]),
                ),
            ),
            order=13,
        ),
        CanvasFeatureProperty(
            id=thickness.id,
            label=thickness.label,
            kind=thickness.kind,
            channels=thickness.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.thickness",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {"value": float(get_divider_widget_state(snap.viewport_state.view_state).thickness)},
            write_snapshot=lambda snap, ch: _set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    thickness=max(0, int(float(ch["value"]))),
                ),
            ),
            order=14,
        ),
    )

def _get_settings_presenter_from_window(presenter):
    window_presenter = getattr(presenter.main_window_app, "presenter", None)
    if window_presenter is not None and hasattr(window_presenter, "get_feature"):
        return window_presenter.get_feature("settings")
    return None

def _toggle_toolbar_orientation(presenter, checked: bool) -> None:
    if presenter.event_bus is not None:
        presenter.event_bus.emit(ViewportToggleOrientationEvent(checked))
        return
    controller = getattr(presenter, "main_controller", None)
    if controller is not None and getattr(controller, "viewport", None) is not None:
        controller.viewport.toggle_orientation(checked)

def _set_toolbar_thickness(presenter, thickness: int) -> None:
    thickness = max(0, int(thickness))
    visible = thickness > 0
    if presenter.event_bus is not None:
        presenter.event_bus.emit(SettingsToggleDividerVisibilityEvent(visible))
        presenter.event_bus.emit(SettingsSetDividerThicknessEvent(thickness))
        return
    controller = getattr(presenter, "main_controller", None)
    if controller is not None and getattr(controller, "viewport", None) is not None:
        _command_set_divider_thickness(_ToolbarViewportAdapter(presenter), thickness)

def _show_divider_color_picker(presenter) -> None:
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter is not None:
        def _apply_selected(color):
            settings_controller = getattr(
                getattr(presenter, "main_controller", None),
                "settings",
                None,
            )
            if settings_controller is not None:
                settings_controller.execute_canvas_feature_command(
                    "divider",
                    "settings.set_color",
                    qcolor_to_color(color),
                )

        def _post_apply(color):
            main_window = getattr(presenter, "main_window_app", None)
            if main_window is not None and hasattr(main_window, "set_divider_button_color"):
                main_window.set_divider_button_color(color)

        settings_presenter.show_canvas_feature_color_picker(
            key="divider",
            setting_key="divider.color",
            title_key="ui.choose_divider_line_color",
            on_selected=_apply_selected,
            post_apply=_post_apply,
        )

def _on_toolbar_middle_clicked(presenter) -> None:
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode != "expert":
        return

    button = presenter.ui.btn_orientation
    current_value = button.get_value()
    if current_value == 0:
        saved_value = button.restore_saved_value()
        target_value = (
            saved_value if (saved_value is not None and saved_value > 0) else 3
        )
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        _set_toolbar_thickness(presenter, target_value)
        return

    button.set_saved_value(current_value)
    button.blockSignals(True)
    button.set_value(0)
    button.blockSignals(False)
    _set_toolbar_thickness(presenter, 0)

def _sync_toolbar_state(presenter) -> None:
    ui = presenter.ui
    viewport = presenter.store.viewport
    divider_state = get_divider_widget_state(viewport.view_state)
    divider_thickness = (
        0
        if not divider_state.visible
        else divider_state.thickness
    )
    ui.btn_orientation.setChecked(
        viewport.view_state.is_horizontal,
        emit_signal=False,
    )
    if ui.btn_orientation.get_value() != divider_thickness:
        ui.btn_orientation.set_value(divider_thickness)
    if hasattr(ui.btn_orientation, "set_color"):
        show_divider_underline = divider_thickness > 0
        ui.btn_orientation.set_color(
            color_to_qcolor(divider_state.color)
            if show_divider_underline
            else None
        )
    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.setChecked(
            viewport.view_state.is_horizontal,
            emit_signal=False,
        )
    if hasattr(ui, "btn_divider_visible"):
        ui.btn_divider_visible.setChecked(
            not divider_state.visible,
            emit_signal=False,
        )
    if hasattr(ui, "btn_divider_width"):
        if ui.btn_divider_width.get_value() != divider_thickness:
            ui.btn_divider_width.set_value(divider_thickness)
    if hasattr(ui, "btn_divider_color") and hasattr(ui.btn_divider_color, "set_color"):
        ui.btn_divider_color.set_color(
            color_to_qcolor(divider_state.color)
        )

def build_divider_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="divider.orientation",
            on_toggled=_toggle_toolbar_orientation,
            on_value_changed=_set_toolbar_thickness,
            on_right_clicked=_show_divider_color_picker,
            on_middle_clicked=_on_toolbar_middle_clicked,
            sync_state=_sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.orientation_simple",
            on_toggled=_toggle_toolbar_orientation,
            sync_state=_sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.visible",
            on_toggled=lambda presenter, checked: _command_toggle_divider_visibility(
                _ToolbarViewportAdapter(presenter),
                not checked,
            ),
            sync_state=_sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.width",
            on_value_changed=_set_toolbar_thickness,
            sync_state=_sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.color",
            on_right_clicked=_show_divider_color_picker,
            sync_state=_sync_toolbar_state,
        ),
    )

class _ToolbarViewportAdapter:
    def __init__(self, presenter):
        self.controller = getattr(presenter, "main_controller", None)
        self.store = presenter.store

def _command_toggle_divider_visibility(actions, visible: bool) -> None:
    if actions.controller.event_bus is not None:
        actions.controller.event_bus.emit(
            SettingsToggleDividerVisibilityEvent(bool(visible))
        )
        return
    settings = getattr(actions.controller, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "divider",
            "settings.toggle_visibility",
            bool(visible),
        )

def _command_set_divider_thickness(actions, thickness: int) -> None:
    thickness = max(0, int(thickness))
    visible = thickness > 0
    if actions.controller.event_bus is not None:
        actions.controller.event_bus.emit(
            SettingsToggleDividerVisibilityEvent(visible)
        )
        actions.controller.event_bus.emit(
            SettingsSetDividerThicknessEvent(thickness)
        )
        actions.controller.update_requested.emit()
        return
    settings = getattr(actions.controller, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "divider",
            "settings.set_thickness",
            thickness,
        )
        return
    actions.controller.update_requested.emit()

def _scale_export_stroke(value: int, scale: float) -> int:
    if value <= 0:
        return 0
    return max(1, int(round(float(value) * max(1.0, float(scale)))))

def _command_build_export_overlay(
    store,
    *,
    scale_x: float,
    scale_y: float,
    content_offset_x: float,
    content_offset_y: float,
    content_width: float,
    content_height: float,
) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "thickness": 0}

    view = viewport.view_state
    divider_state = get_divider_widget_state(view)
    is_horizontal = bool(view.is_horizontal)
    thickness = _scale_export_stroke(
        int(divider_state.thickness),
        scale_y if is_horizontal else scale_x,
    )
    split_pos = int(
        round(
            (content_offset_y + (content_height * float(view.split_position_visual)))
            if is_horizontal
            else (content_offset_x + (content_width * float(view.split_position_visual)))
        )
    )
    return {
        "visible": bool(divider_state.visible and str(view.diff_mode or "off") == "off"),
        "split_pos": split_pos,
        "is_horizontal": is_horizontal,
        "color": color_to_qcolor(divider_state.color),
        "thickness": thickness,
    }

def _command_build_render_canvas_payload(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "color": (255, 255, 255, 255), "thickness": 0}
    divider_state = get_divider_widget_state(viewport.view_state)
    color = divider_state.color
    return {
        "visible": bool(divider_state.visible),
        "color": (int(color.r), int(color.g), int(color.b), int(color.a)),
        "thickness": int(divider_state.thickness),
    }

def _command_build_runtime_overlay_style(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "color": color_to_qcolor(Color()), "thickness": 0}
    divider_state = get_divider_widget_state(viewport.view_state)
    return {
        "visible": bool(divider_state.visible),
        "color": color_to_qcolor(divider_state.color),
        "thickness": int(divider_state.thickness),
    }

def build_divider_commands() -> dict[str, Any]:
    return {
        "viewport.toggle_visibility": _command_toggle_divider_visibility,
        "viewport.set_thickness": _command_set_divider_thickness,
        "settings.toggle_visibility": lambda settings, visible: settings.mutations.set_canvas_feature_setting(
            "divider.visible",
            bool(visible),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "divider.color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_thickness": lambda settings, thickness: settings.mutations.set_canvas_feature_setting(
            "divider.thickness",
            max(0, min(20, int(thickness))),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "export.overlay": _command_build_export_overlay,
        "render.canvas_payload": _command_build_render_canvas_payload,
        "runtime.overlay_style": _command_build_runtime_overlay_style,
    }

def build_divider_settings_event_bindings() -> tuple[CanvasFeatureSettingsEventBinding, ...]:
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleDividerVisibilityEvent,
            command_id="settings.toggle_visibility",
            extract_args=lambda event: (event.visible,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetDividerThicknessEvent,
            command_id="settings.set_thickness",
            extract_args=lambda event: (event.thickness,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetDividerColorEvent,
            command_id="settings.set_color",
            extract_args=lambda event: (event.color,),
        ),
    )

def build_divider_render_scene_overrides(store) -> dict[str, Any]:
    from domain.qt_adapters import color_to_qcolor

    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}

    view = viewport.view_state
    divider_state = get_divider_widget_state(view)
    diff_mode = str(getattr(view, "diff_mode", "off") or "off")
    single_image_mode = int(getattr(view, "showing_single_image_mode", 0) or 0)
    return {
        "show_divider": bool(
            divider_state.visible
            and diff_mode == "off"
            and single_image_mode == 0
        ),
        "divider_color": color_to_qcolor(divider_state.color),
        "divider_thickness": int(divider_state.thickness),
        "filename_divider_thickness": int(divider_state.thickness),
    }

WIDGET_FEATURE = CanvasWidgetFeature(
    name="divider",
    reduce_view_state=reduce_divider_view_state,
    reduce_render_config=reduce_divider_render_config,
    build_properties=build_divider_properties,
    build_toolbar_bindings=build_divider_toolbar_bindings,
    build_commands=build_divider_commands,
    build_settings_event_bindings=build_divider_settings_event_bindings,
    build_render_scene_overrides=build_divider_render_scene_overrides,
    reducer_order=10,
    property_order=10,
)
