from __future__ import annotations

from core.state_management.action_base import Action
from core.state_management.appearance_actions import (
    SetDrawTextBackgroundAction,
    SetFileNameBgColorAction,
    SetFileNameColorAction,
    SetFontSizePercentAction,
    SetFontWeightAction,
    SetIncludeFileNamesInSavedAction,
    SetMaxNameLengthAction,
    SetTextAlphaPercentAction,
    SetTextPlacementModeAction,
)
from core.store_viewport import RenderConfig
from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor
from tabs.image_compare.canvas.features.filename_overlay.events import (
    SettingsToggleIncludeFilenamesInSavedEvent,
)
from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from tabs.image_compare.canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS

from .config import FilenameOverlayConfig


def reduce_filename_overlay_render_config(
    config: RenderConfig, action: Action
) -> RenderConfig:
    from dataclasses import replace

    if isinstance(action, SetIncludeFileNamesInSavedAction):
        return replace(config, include_file_names_in_saved=action.enabled)
    if isinstance(action, SetFontSizePercentAction):
        return replace(config, font_size_percent=action.size)
    if isinstance(action, SetFontWeightAction):
        return replace(config, font_weight=action.weight)
    if isinstance(action, SetTextAlphaPercentAction):
        return replace(config, text_alpha_percent=action.alpha)
    if isinstance(action, SetFileNameColorAction):
        return replace(config, file_name_color=action.color)
    if isinstance(action, SetFileNameBgColorAction):
        return replace(config, file_name_bg_color=action.color)
    if isinstance(action, SetDrawTextBackgroundAction):
        return replace(config, draw_text_background=action.enabled)
    if isinstance(action, SetTextPlacementModeAction):
        return replace(config, text_placement_mode=action.mode)
    if isinstance(action, SetMaxNameLengthAction):
        return replace(config, max_name_length=action.length)
    return config


def build_filename_overlay_properties() -> tuple[CanvasFeatureProperty, ...]:
    bool_channels = (
        ChannelDescriptor("value", "Value", "bool", interpolate_values=False),
    )
    scalar_channels = (ChannelDescriptor("value", "Value", "scalar"),)
    enum_channels = (
        ChannelDescriptor("value", "Value", "enum", interpolate_values=False),
    )
    color_channels = (
        ChannelDescriptor("r", "R", "color"),
        ChannelDescriptor("g", "G", "color"),
        ChannelDescriptor("b", "B", "color"),
        ChannelDescriptor("a", "A", "color"),
    )
    return (
        CanvasFeatureProperty(
            id="filename_overlay.visible",
            label="Visible",
            kind="bool",
            channels=bool_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="include_file_names_in_saved",
            read_snapshot=lambda snap: {
                "value": bool(
                    snap.viewport_state.render_config.include_file_names_in_saved
                )
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "include_file_names_in_saved",
                bool(ch["value"]),
            ),
            order=40,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.font_size",
            label="Font Size",
            kind="scalar",
            channels=scalar_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="font_size_percent",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {
                "value": float(snap.viewport_state.render_config.font_size_percent)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "font_size_percent",
                max(1, int(float(ch["value"]))),
            ),
            order=41,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.font_weight",
            label="Font Weight",
            kind="scalar",
            channels=scalar_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="font_weight",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {
                "value": float(snap.viewport_state.render_config.font_weight)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "font_weight",
                max(0, int(float(ch["value"]))),
            ),
            order=42,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.text_alpha",
            label="Text Alpha",
            kind="scalar",
            channels=scalar_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="text_alpha_percent",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {
                "value": float(snap.viewport_state.render_config.text_alpha_percent)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "text_alpha_percent",
                max(5, min(100, int(float(ch["value"])))),
            ),
            order=43,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.text_color",
            label="Text Color",
            kind="color",
            channels=color_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="filename_color",
            read_snapshot=lambda snap: {
                "r": int(snap.viewport_state.render_config.file_name_color.r),
                "g": int(snap.viewport_state.render_config.file_name_color.g),
                "b": int(snap.viewport_state.render_config.file_name_color.b),
                "a": int(snap.viewport_state.render_config.file_name_color.a),
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "file_name_color",
                Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
            ),
            order=44,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.background_color",
            label="Background Color",
            kind="color",
            channels=color_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="filename_bg_color",
            read_snapshot=lambda snap: {
                "r": int(snap.viewport_state.render_config.file_name_bg_color.r),
                "g": int(snap.viewport_state.render_config.file_name_bg_color.g),
                "b": int(snap.viewport_state.render_config.file_name_bg_color.b),
                "a": int(snap.viewport_state.render_config.file_name_bg_color.a),
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "file_name_bg_color",
                Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
            ),
            order=45,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.draw_background",
            label="Draw Background",
            kind="bool",
            channels=bool_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="draw_text_background",
            read_snapshot=lambda snap: {
                "value": bool(snap.viewport_state.render_config.draw_text_background)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "draw_text_background",
                bool(ch["value"]),
            ),
            order=46,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.placement_mode",
            label="Placement",
            kind="enum",
            channels=enum_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="text_placement_mode",
            read_snapshot=lambda snap: {
                "value": str(snap.viewport_state.render_config.text_placement_mode)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "text_placement_mode",
                str(ch["value"]),
            ),
            order=47,
        ),
        CanvasFeatureProperty(
            id="filename_overlay.max_name_length",
            label="Max Name Length",
            kind="scalar",
            channels=scalar_channels,
            group_id="filename_overlay",
            group_label="Filename Overlay",
            setting_key="max_name_length",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {
                "value": float(snap.viewport_state.render_config.max_name_length)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.render_config,
                "max_name_length",
                max(1, int(float(ch["value"]))),
            ),
            order=48,
        ),
    )


def _command_toggle_filename_overlay(actions, enabled: bool) -> None:
    settings = getattr(actions, "settings", None)
    if settings is None:
        controller = getattr(actions, "main_controller", None)
        settings = (
            getattr(controller, "settings", None) if controller is not None else None
        )
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "filename_overlay",
            "settings.toggle_visibility",
            bool(enabled),
        )


def _sync_filename_overlay_toolbar_state(presenter) -> None:
    control = getattr(getattr(presenter, "ui", None), "btn_file_names", None)
    if control is None:
        return
    enabled = bool(presenter.store.viewport.render_config.include_file_names_in_saved)
    if control.isChecked() != enabled:
        control.setChecked(enabled, emit_signal=False)


def build_filename_overlay_toolbar_bindings() -> (
    tuple[CanvasFeatureToolbarBinding, ...]
):
    return (
        CanvasFeatureToolbarBinding(
            control_id="filename_overlay.visible",
            on_toggled=_command_toggle_filename_overlay,
            sync_state=_sync_filename_overlay_toolbar_state,
        ),
    )


def build_filename_overlay_commands() -> dict[str, object]:
    return {
        "settings.toggle_visibility": lambda settings, enabled: settings.mutations.set_canvas_feature_setting(
            "include_file_names_in_saved",
            bool(enabled),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_font_size": lambda settings, size: settings.mutations.set_canvas_feature_setting(
            "font_size_percent",
            max(1, int(size)),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_font_weight": lambda settings, weight: settings.mutations.set_canvas_feature_setting(
            "font_weight",
            max(0, int(weight)),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_text_alpha": lambda settings, alpha: settings.mutations.set_canvas_feature_setting(
            "text_alpha_percent",
            max(5, min(100, int(alpha))),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_text_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "filename_color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_background_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "filename_bg_color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_draw_background": lambda settings, enabled: settings.mutations.set_canvas_feature_setting(
            "draw_text_background",
            bool(enabled),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_placement_mode": lambda settings, mode: settings.mutations.set_canvas_feature_setting(
            "text_placement_mode",
            str(mode),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_max_name_length": lambda settings, length: settings.mutations.set_canvas_feature_setting(
            "max_name_length",
            max(1, int(length)),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
    }


def build_filename_overlay_settings_event_bindings() -> (
    tuple[CanvasFeatureSettingsEventBinding, ...]
):
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleIncludeFilenamesInSavedEvent,
            command_id="settings.toggle_visibility",
            extract_args=lambda event: (event.include,),
        ),
    )


def build_filename_overlay_render_scene_overrides(store) -> dict:
    viewport = getattr(store, "viewport", None)
    document = getattr(store, "document", None)
    if viewport is None:
        return {"filename_overlay": FilenameOverlayConfig()}

    is_horizontal = bool(getattr(viewport.view_state, "is_horizontal", False))
    split_position_visual = float(
        getattr(viewport.view_state, "split_position_visual", 0.5)
    )
    divider_style = {}
    query_divider_style = get_canvas_feature_command_by_alias("splitter.overlay_style")
    if query_divider_style is not None:
        divider_style = query_divider_style(store) or {}

    image_display_rect = getattr(
        viewport.geometry_state, "image_display_rect_on_label", None
    )
    if image_display_rect is not None:
        image_display_rect = (
            int(getattr(image_display_rect, "x", 0)),
            int(getattr(image_display_rect, "y", 0)),
            int(getattr(image_display_rect, "w", 0)),
            int(getattr(image_display_rect, "h", 0)),
        )

    return {
        "filename_overlay": FilenameOverlayConfig(
            enabled=bool(
                getattr(viewport.render_config, "include_file_names_in_saved", False)
            ),
            image_display_rect=image_display_rect,
            text_placement_mode=str(
                getattr(viewport.render_config, "text_placement_mode", "edges")
            ),
            split_position=split_position_visual,
            is_horizontal=is_horizontal,
            divider_thickness=int(divider_style.get("thickness", 0)),
            is_interactive_mode=bool(
                getattr(viewport.interaction_state, "is_interactive_mode", False)
            ),
            draw_text_background=bool(
                getattr(viewport.render_config, "draw_text_background", True)
            ),
            font_base_pixel_size=DEFAULT_CANVAS_STYLE_TOKENS.filename_font_base_du,
            font_size_percent=int(
                getattr(viewport.render_config, "font_size_percent", 100)
            ),
            font_weight=int(getattr(viewport.render_config, "font_weight", 0)),
            text_alpha_percent=int(
                getattr(viewport.render_config, "text_alpha_percent", 100)
            ),
            file_name_color=getattr(viewport.render_config, "file_name_color", None),
            file_name_bg_color=getattr(
                viewport.render_config, "file_name_bg_color", None
            ),
            max_name_length=int(getattr(viewport.render_config, "max_name_length", 50)),
            name1=document.get_active_display_name(1) if document is not None else "",
            name2=document.get_active_display_name(2) if document is not None else "",
        )
    }


def build_filename_overlay_state_queries():
    """Build state queries for direct feature state access."""
    return ()


def build_filename_overlay_state_commands():
    """Build state commands for direct feature state modification."""
    return ()


FILENAME_OVERLAY_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias(
        "labels.settings.toggle_visibility", "settings.toggle_visibility"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_font_size", "settings.set_font_size"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_font_weight", "settings.set_font_weight"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_text_color", "settings.set_text_color"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_background_color", "settings.set_background_color"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_draw_background", "settings.set_draw_background"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_placement_mode", "settings.set_placement_mode"
    ),
    CanvasFeatureCommandAlias(
        "labels.settings.set_text_alpha", "settings.set_text_alpha"
    ),
)


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="filename_overlay",
        reduce_view_state=lambda vs, a: vs,
        reduce_render_config=reduce_filename_overlay_render_config,
        build_properties=build_filename_overlay_properties,
        build_toolbar_bindings=build_filename_overlay_toolbar_bindings,
        build_commands=build_filename_overlay_commands,
        command_aliases=FILENAME_OVERLAY_COMMAND_ALIASES,
        build_settings_event_bindings=build_filename_overlay_settings_event_bindings,
        build_state_queries=build_filename_overlay_state_queries,
        build_state_commands=build_filename_overlay_state_commands,
        build_render_scene_overrides=build_filename_overlay_render_scene_overrides,
        i18n_namespace="ui.labels",
        reducer_order=40,
        property_order=40,
    )


WIDGET_FEATURE = build_widget_feature()
