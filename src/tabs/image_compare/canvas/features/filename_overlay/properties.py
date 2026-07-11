from __future__ import annotations

from domain.types import Color
from shared.keyframing.adapters_base import ChannelDescriptor
from ui.canvas_infra.scene.widget_contract import CanvasFeatureProperty


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
