from __future__ import annotations

import copy
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Set

from domain.types import Color, Point, Rect

logger = logging.getLogger("ImproveImgSLI")

@dataclass
class MagnifierModel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    visible: bool = True
    position: Point = field(default_factory=lambda: Point(0.5, 0.5))
    size_relative: float = 0.2
    capture_size_relative: float = 0.1

    border_color: Color = field(default_factory=lambda: Color(255, 255, 255, 230))
    divider_color: Color = field(default_factory=lambda: Color(255, 255, 255, 230))
    laser_color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    capture_ring_color: Color = field(default_factory=lambda: Color(255, 50, 100, 230))

    offset_relative: Point = field(default_factory=lambda: Point(0.0, 0.0))
    spacing_relative: float = 0.05
    is_horizontal: bool = False
    internal_split: float = 0.5
    divider_visible: bool = True
    divider_thickness: int = 2
    border_thickness: int = 2
    visible_left: bool = True
    visible_center: bool = True
    visible_right: bool = True
    freeze: bool = False
    frozen_position: Optional[Point] = None
    show_capture_area: bool = True
    interpolation_method: str = "BILINEAR"

    def clone(self):
        return copy.copy(self)

@dataclass
class RenderConfig:
    interpolation_method: str = "BILINEAR"
    zoom_interpolation_method: str = "BILINEAR"
    movement_interpolation_method: str = "BILINEAR"
    magnifier_movement_interpolation_method: str = "BILINEAR"
    display_resolution_limit: int = 0
    jpeg_quality: int = 95

    include_file_names_in_saved: bool = False
    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: Color = field(default_factory=lambda: Color(255, 0, 0, 255))
    file_name_bg_color: Color = field(default_factory=lambda: Color(0, 0, 0, 80))
    draw_text_background: bool = True
    text_placement_mode: str = "edges"
    max_name_length: int = 50

    def clone(self):
        return copy.copy(self)

    def to_dict(self) -> dict:
        return {
            "interpolation_method": self.interpolation_method,
            "zoom_interpolation_method": self.zoom_interpolation_method,
            "movement_interpolation_method": self.movement_interpolation_method,
            "magnifier_movement_interpolation_method": self.magnifier_movement_interpolation_method,
            "display_resolution_limit": self.display_resolution_limit,
            "jpeg_quality": self.jpeg_quality,
            "include_file_names_in_saved": self.include_file_names_in_saved,
            "font_size_percent": self.font_size_percent,
            "font_weight": self.font_weight,
            "text_alpha_percent": self.text_alpha_percent,
            "file_name_color": (
                self.file_name_color.r,
                self.file_name_color.g,
                self.file_name_color.b,
                self.file_name_color.a,
            ),
            "file_name_bg_color": (
                self.file_name_bg_color.r,
                self.file_name_bg_color.g,
                self.file_name_bg_color.b,
                self.file_name_bg_color.a,
            ),
            "draw_text_background": self.draw_text_background,
            "text_placement_mode": self.text_placement_mode,
            "max_name_length": self.max_name_length,
        }

@dataclass
class ImageSessionState:
    image1: Optional[Any] = None
    image2: Optional[Any] = None

    loaded_image1_paths: list[str] = field(default_factory=list)
    loaded_image2_paths: list[str] = field(default_factory=list)
    loaded_current_index1: int = -1
    loaded_current_index2: int = -1

    auto_calculate_psnr: bool = False
    auto_calculate_ssim: bool = False
    psnr_value: Optional[float] = None
    ssim_value: Optional[float] = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.loaded_image1_paths = list(self.loaded_image1_paths)
        new_obj.loaded_image2_paths = list(self.loaded_image2_paths)
        return new_obj

@dataclass
class RenderCacheState:

    display_cache_image1: Optional[Any] = None
    display_cache_image2: Optional[Any] = None
    scaled_image1_for_display: Optional[Any] = None
    scaled_image2_for_display: Optional[Any] = None
    cached_scaled_image_dims: Optional[tuple[int, int]] = None
    last_display_cache_params: Optional[tuple] = None

    unified_image_cache: OrderedDict = field(default_factory=OrderedDict)
    unification_in_progress: bool = False
    pending_unification_paths: Optional[tuple[str, str]] = None

    caches: dict = field(default_factory=dict)
    magnifier_cache: dict = field(default_factory=dict)
    cached_split_base_image: Optional[Any] = None
    last_split_cached_params: Optional[tuple] = None
    cached_diff_image: Optional[Any] = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.unified_image_cache = self.unified_image_cache.__class__(
            self.unified_image_cache
        )
        new_obj.caches = dict(self.caches)
        new_obj.magnifier_cache = dict(self.magnifier_cache)
        return new_obj

class SessionData:
    __slots__ = ("_image_state", "_render_cache")

    def __init__(
        self,
        image_state: Optional[ImageSessionState] = None,
        render_cache: Optional[RenderCacheState] = None,
    ):
        self._image_state = image_state or ImageSessionState()
        self._render_cache = render_cache or RenderCacheState()

    @property
    def image_state(self) -> ImageSessionState:
        return self._image_state

    @image_state.setter
    def image_state(self, val):
        self._image_state = val

    @property
    def render_cache(self) -> RenderCacheState:
        return self._render_cache

    @render_cache.setter
    def render_cache(self, val):
        self._render_cache = val

    def clone(self):
        return SessionData(
            image_state=self._image_state.clone(),
            render_cache=self._render_cache.clone(),
        )

@dataclass
class GeometryState:
    pixmap_width: int = 0
    pixmap_height: int = 0
    image_display_rect_on_label: Rect = field(default_factory=lambda: Rect())
    fixed_label_width: Optional[int] = None
    fixed_label_height: Optional[int] = None

    magnifier_screen_center: Point = field(default_factory=lambda: Point())
    magnifier_screen_size: int = 0

    loaded_geometry: bytes = b""
    loaded_was_maximized: bool = False
    loaded_previous_geometry: bytes = b""
    loaded_debug_mode_enabled: bool = False

    def clone(self):
        return copy.copy(self)

@dataclass
class InteractionState:
    resize_in_progress: bool = False

    is_interactive_mode: bool = False
    is_dragging_split_line: bool = False
    is_dragging_capture_point: bool = False
    is_dragging_split_in_magnifier: bool = False
    is_dragging_any_slider: bool = False
    interaction_session_id: int = 0
    is_user_interacting: bool = False
    pressed_keys: Set[int] = field(default_factory=set)
    last_horizontal_movement_key: int | None = None
    last_vertical_movement_key: int | None = None
    last_spacing_movement_key: int | None = None
    space_bar_pressed: bool = False
    magnifier_offset_relative_visual: Point = field(
        default_factory=lambda: Point(0.0, 0.0)
    )
    magnifier_spacing_relative_visual: float = 0.1
    magnifier_internal_split_visual: float = 0.5

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.pressed_keys = set(self.pressed_keys)
        return new_obj

@dataclass
class ViewState:
    split_position: float = 0.5
    split_position_visual: float = 0.5
    is_horizontal: bool = False

    diff_mode: str = "off"
    channel_view_mode: str = "RGB"

    canvas_widget_state: dict[str, Any] = field(default_factory=dict)
    optimize_magnifier_movement: bool = True

    highlighted_magnifier_element: Optional[str] = None

    showing_single_image_mode: int = 0
    movement_speed_per_sec: float = 2.0
    text_bg_visual_height: float = 0.0
    text_bg_visual_width: float = 0.0

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.canvas_widget_state = copy.deepcopy(self.canvas_widget_state)
        return new_obj

class ViewportState:
    __slots__ = (
        "_render_config",
        "_session_data",
        "_view_state",
        "_interaction_state",
        "_geometry_state",
        "_viewport_plugin_state",
        "_analysis_plugin_state",
        "_last_source1_id",
        "_last_source2_id",
        "_last_render_params",
        "_divider_clip_rect",
    )

    def __init__(
        self,
        render_config: Optional[RenderConfig] = None,
        session_data: Optional[SessionData] = None,
        view_state: Optional[ViewState] = None,
        interaction_state: Optional[InteractionState] = None,
        geometry_state: Optional[GeometryState] = None,
    ):
        self._render_config = render_config or RenderConfig()
        self._session_data = session_data or SessionData()
        self._view_state = view_state or ViewState()
        self._interaction_state = interaction_state or InteractionState()
        self._geometry_state = geometry_state or GeometryState()
        self._viewport_plugin_state = None
        self._analysis_plugin_state = None
        self._last_source1_id = 0
        self._last_source2_id = 0
        self._last_render_params = None
        self._divider_clip_rect = None

    @property
    def render_config(self) -> RenderConfig:
        return self._render_config

    @render_config.setter
    def render_config(self, val):
        self._render_config = val

    @property
    def session_data(self) -> SessionData:
        return self._session_data

    @session_data.setter
    def session_data(self, val):
        self._session_data = val

    @property
    def view_state(self) -> ViewState:
        return self._view_state

    @view_state.setter
    def view_state(self, val):
        self._view_state = val

    @property
    def interaction_state(self) -> InteractionState:
        return self._interaction_state

    @interaction_state.setter
    def interaction_state(self, val):
        self._interaction_state = val

    @property
    def geometry_state(self) -> GeometryState:
        return self._geometry_state

    @geometry_state.setter
    def geometry_state(self, val):
        self._geometry_state = val

    @property
    def divider_clip_rect(self):
        return self._divider_clip_rect

    @divider_clip_rect.setter
    def divider_clip_rect(self, val):
        self._divider_clip_rect = val

    def set_viewport_plugin_state(self, state: Any):
        self._viewport_plugin_state = state
        if state is not None:
            for field_name in getattr(state, "__dataclass_fields__", {}):
                if hasattr(self, field_name):
                    setattr(state, field_name, getattr(self, field_name))

    def set_analysis_plugin_state(self, state: Any):
        self._analysis_plugin_state = state
        if state is not None:
            for field_name in getattr(state, "__dataclass_fields__", {}):
                if hasattr(self.view_state, field_name):
                    setattr(state, field_name, getattr(self.view_state, field_name))

    def clone(self):
        new_obj = ViewportState(
            render_config=self._render_config.clone(),
            session_data=self._session_data.clone(),
            view_state=self._view_state.clone(),
            interaction_state=self._interaction_state.clone(),
            geometry_state=self._geometry_state.clone(),
        )
        new_obj._viewport_plugin_state = self._viewport_plugin_state
        new_obj._analysis_plugin_state = self._analysis_plugin_state
        new_obj._last_source1_id = self._last_source1_id
        new_obj._last_source2_id = self._last_source2_id
        new_obj._last_render_params = self._last_render_params
        new_obj._divider_clip_rect = self._divider_clip_rect
        return new_obj

    def clone_visual_state(self):
        return self.clone()

    def freeze_for_export(self):
        frozen = self.clone()
        frozen.view_state.showing_single_image_mode = 0
        frozen.interaction_state.space_bar_pressed = False
        frozen.interaction_state.pressed_keys = set()
        frozen.interaction_state.is_dragging_split_line = False
        frozen.interaction_state.is_dragging_capture_point = False
        frozen.interaction_state.is_dragging_split_in_magnifier = False
        frozen.interaction_state.is_dragging_any_slider = False
        frozen.interaction_state.is_interactive_mode = False
        frozen.interaction_state.is_user_interacting = False
        return frozen

    def get_render_params(self) -> dict:
        params = self._render_config.to_dict()
        from ui.canvas_infra.scene.widget_registry import get_canvas_feature_commands
        from ui.canvas_features.magnifier import MagnifierStoreService
        from ui.canvas_features.magnifier.state import get_magnifier_widget_state
        from ui.canvas_features.magnifier.store import (
            default_capture_size,
            default_magnifier_size,
            magnifier_enabled,
        )

        view = self._view_state
        render = self._render_config
        scene_state = MagnifierStoreService(type("StoreProxy", (), {"viewport": self})())
        store_proxy = type("StoreProxy", (), {"viewport": self})()
        magnifier = scene_state.get_active_or_first_magnifier()
        magnifier_state = get_magnifier_widget_state(view)
        all_models = iter_magnifier_models(view, render)
        magnifier_capture_areas = [
            (
                float(model.position.x),
                float(model.position.y),
                float(model.capture_size_relative),
            )
            for model in all_models
            if bool(model.visible) and bool(getattr(model, "show_capture_area", True))
        ]
        if magnifier is None:
            mag_pos = (0.5, 0.5)
            mag_offset_visual = (0.0, 0.0)
            mag_spacing = 0.0
            magnifier_size = default_magnifier_size(view)
            capture_size = default_capture_size(view)
            magnifier_is_horizontal = False
            magnifier_internal_split = 0.5
            magnifier_visible_left = True
            magnifier_visible_center = True
            magnifier_visible_right = True
            is_magnifier_combined = False
            magnifier_divider_visible = magnifier_state.default_divider_visible
            magnifier_divider_color = magnifier_state.default_divider_color
            magnifier_divider_thickness = magnifier_state.default_divider_thickness
            magnifier_border_color = magnifier_state.default_border_color
        else:
            mag_pos = (magnifier.position.x, magnifier.position.y)
            mag_offset_obj = magnifier.offset_relative
            mag_spacing = magnifier.spacing_relative
            mag_offset_visual = (mag_offset_obj.x, mag_offset_obj.y)
            magnifier_size = magnifier.size_relative
            capture_size = magnifier.capture_size_relative
            magnifier_is_horizontal = magnifier.is_horizontal
            magnifier_internal_split = magnifier.internal_split
            magnifier_visible_left = magnifier.visible_left
            magnifier_visible_center = magnifier.visible_center
            magnifier_visible_right = magnifier.visible_right
            is_magnifier_combined = scene_state.is_active_magnifier_combined()
            magnifier_divider_visible = magnifier.divider_visible
            magnifier_divider_color = magnifier.divider_color
            magnifier_divider_thickness = magnifier.divider_thickness
            magnifier_border_color = magnifier.border_color

        interaction = self._interaction_state
        mag_offset_real = magnifier.offset_relative if magnifier is not None else Point(0.0, 0.0)
        mag_spacing_real = magnifier.spacing_relative if magnifier is not None else 0.0
        mag_offset_visual_obj = interaction.magnifier_offset_relative_visual
        mag_spacing_visual = interaction.magnifier_spacing_relative_visual

        if magnifier_enabled(view) and interaction.is_interactive_mode:
            mag_offset_visual = (
                interaction.magnifier_offset_relative_visual.x,
                interaction.magnifier_offset_relative_visual.y,
            )
            mag_spacing = interaction.magnifier_spacing_relative_visual
        is_interactive = interaction.is_interactive_mode
        split_pos_real = view.split_position
        split_pos_visual = view.split_position_visual

        if is_interactive:
            split_pos = split_pos_real
        else:
            offset_match = (
                abs(mag_offset_real.x - mag_offset_visual_obj.x) < 0.001
                and abs(mag_offset_real.y - mag_offset_visual_obj.y) < 0.001
            )
            spacing_match = abs(mag_spacing_real - mag_spacing_visual) < 0.001
            split_match = abs(split_pos_real - split_pos_visual) < 0.001

            split_pos = (
                split_pos_visual
                if (offset_match and spacing_match and split_match)
                else split_pos_real
            )

        from core.constants import AppConstants

        main_interp = render.interpolation_method
        optimize_mag_mov = getattr(view, "optimize_magnifier_movement", True)
        magnifier_movement_interp = getattr(
            render, "magnifier_movement_interpolation_method", "BILINEAR"
        )
        from ui.canvas_features.guides.state import get_guides_widget_state

        guides_state = get_guides_widget_state(view)
        laser_smoothing_interp = guides_state.smoothing_interpolation_method

        def resolve(option: str) -> str:
            main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_interp, 999)
            option_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(option, 999)
            return main_interp if main_speed <= option_speed else option

        eff_mag_mov = (
            resolve(magnifier_movement_interp) if optimize_mag_mov else main_interp
        )
        eff_laser = resolve(laser_smoothing_interp)

        canvas_feature_render_payloads = {}
        for feature_name, commands in get_canvas_feature_commands().items():
            payload_command = commands.get("render.canvas_payload")
            if payload_command is None:
                continue
            canvas_feature_render_payloads[feature_name] = payload_command(store_proxy)

        params.update(
            {
                "canvas_feature_render_payloads": canvas_feature_render_payloads,
                "split_pos": split_pos,
                "magnifier_position": mag_pos,
                "magnifier_visual_offset": mag_offset_visual,
                "magnifier_visual_spacing": mag_spacing,
                "magnifier_size": magnifier_size,
                "capture_size": capture_size,
                "is_horizontal": view.is_horizontal,
                "magnifier_layout_horizontal": magnifier_is_horizontal,
                "magnifier_split": magnifier_internal_split,
                "magnifier_enabled": magnifier_enabled(view),
                "magnifier_show_left": magnifier_visible_left,
                "magnifier_show_center": magnifier_visible_center,
                "magnifier_show_right": magnifier_visible_right,
                "magnifier_combined": is_magnifier_combined,
                "magnifier_divider_visible": bool(magnifier_divider_visible),
                "magnifier_divider_color": (
                    int(magnifier_divider_color.r),
                    int(magnifier_divider_color.g),
                    int(magnifier_divider_color.b),
                    int(magnifier_divider_color.a),
                ),
                "magnifier_divider_thickness": int(magnifier_divider_thickness),
                "magnifier_border_color": (
                    int(magnifier_border_color.r),
                    int(magnifier_border_color.g),
                    int(magnifier_border_color.b),
                    int(magnifier_border_color.a),
                ),
                "magnifier_capture_areas": magnifier_capture_areas,
                "diff_mode": view.diff_mode,
                "channel_view_mode": view.channel_view_mode,
                "is_interactive_mode": interaction.is_interactive_mode,
                "highlighted_magnifier_element": view.highlighted_magnifier_element,
                "highlight_capture": interaction.is_dragging_capture_point,
                "movement_interpolation_method": eff_mag_mov,
                "magnifier_movement_interpolation_method": eff_mag_mov,
                "laser_smoothing_interpolation_method": eff_laser,
            }
        )
        return params
