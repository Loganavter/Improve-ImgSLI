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
    laser_color: Color = field(default_factory=lambda: Color(255, 255, 255, 120))
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
    divider_line_visible: bool = True
    divider_line_color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    divider_line_thickness: int = 3

    magnifier_divider_visible: bool = True
    magnifier_divider_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 230)
    )
    magnifier_divider_thickness: int = 2

    magnifier_border_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 248)
    )
    magnifier_laser_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 255)
    )
    capture_ring_color: Color = field(default_factory=lambda: Color(255, 50, 100, 230))
    show_magnifier_guides: bool = False
    magnifier_guides_thickness: int = 1

    interpolation_method: str = "BILINEAR"
    zoom_interpolation_method: str = "BILINEAR"
    movement_interpolation_method: str = "BILINEAR"
    magnifier_movement_interpolation_method: str = "BILINEAR"
    laser_smoothing_interpolation_method: str = "BILINEAR"
    optimize_laser_smoothing: bool = False
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

    show_capture_area_on_main_image: bool = True

    def clone(self):
        return copy.copy(self)

    def to_dict(self) -> dict:
        return {
            "divider_line_visible": self.divider_line_visible,
            "divider_line_color": (
                self.divider_line_color.r,
                self.divider_line_color.g,
                self.divider_line_color.b,
                self.divider_line_color.a,
            ),
            "divider_line_thickness": self.divider_line_thickness,
            "magnifier_divider_visible": self.magnifier_divider_visible,
            "magnifier_divider_color": (
                self.magnifier_divider_color.r,
                self.magnifier_divider_color.g,
                self.magnifier_divider_color.b,
                self.magnifier_divider_color.a,
            ),
            "magnifier_divider_thickness": self.magnifier_divider_thickness,
            "magnifier_border_color": (
                self.magnifier_border_color.r,
                self.magnifier_border_color.g,
                self.magnifier_border_color.b,
                self.magnifier_border_color.a,
            ),
            "magnifier_laser_color": (
                self.magnifier_laser_color.r,
                self.magnifier_laser_color.g,
                self.magnifier_laser_color.b,
                self.magnifier_laser_color.a,
            ),
            "capture_ring_color": (
                self.capture_ring_color.r,
                self.capture_ring_color.g,
                self.capture_ring_color.b,
                self.capture_ring_color.a,
            ),
            "show_magnifier_guides": self.show_magnifier_guides,
            "magnifier_guides_thickness": self.magnifier_guides_thickness,
            "interpolation_method": self.interpolation_method,
            "zoom_interpolation_method": self.zoom_interpolation_method,
            "movement_interpolation_method": self.movement_interpolation_method,
            "magnifier_movement_interpolation_method": self.magnifier_movement_interpolation_method,
            "laser_smoothing_interpolation_method": self.laser_smoothing_interpolation_method,
            "optimize_laser_smoothing": self.optimize_laser_smoothing,
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
            "show_capture_area_on_main_image": self.show_capture_area_on_main_image,
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

    use_magnifier: bool = False
    magnifiers: dict[str, MagnifierModel] = field(default_factory=dict)
    active_magnifier_id: Optional[str] = None
    magnifier_size_relative: float = 0.2
    capture_size_relative: float = 0.1
    capture_position_relative: Point = field(default_factory=lambda: Point(0.5, 0.5))
    freeze_magnifier: bool = False
    frozen_capture_point_relative: Optional[Point] = None
    magnifier_offset_relative: Point = field(default_factory=lambda: Point(0.0, 0.0))
    magnifier_spacing_relative: float = 0.1
    magnifier_offset_relative_visual: Point = field(
        default_factory=lambda: Point(0.0, 0.0)
    )
    magnifier_spacing_relative_visual: float = 0.1
    magnifier_is_horizontal: bool = False
    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    magnifier_internal_split: float = 0.5
    is_magnifier_combined: bool = False
    optimize_magnifier_movement: bool = True

    highlighted_magnifier_element: Optional[str] = None

    showing_single_image_mode: int = 0
    movement_speed_per_sec: float = 2.0
    text_bg_visual_height: float = 0.0
    text_bg_visual_width: float = 0.0

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.magnifiers = {key: value.clone() for key, value in self.magnifiers.items()}
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

        view = self._view_state
        render = self._render_config
        capture_pos = view.capture_position_relative
        mag_pos = (capture_pos.x, capture_pos.y)

        interaction = self._interaction_state
        is_interactive = interaction.is_interactive_mode

        mag_offset_real = view.magnifier_offset_relative
        mag_offset_visual_obj = view.magnifier_offset_relative_visual
        mag_spacing_real = view.magnifier_spacing_relative
        mag_spacing_visual = view.magnifier_spacing_relative_visual
        split_pos_real = view.split_position
        split_pos_visual = view.split_position_visual

        if is_interactive:
            mag_offset_obj = mag_offset_real
            mag_spacing = mag_spacing_real
            split_pos = split_pos_real
        else:
            offset_match = (
                abs(mag_offset_real.x - mag_offset_visual_obj.x) < 0.001
                and abs(mag_offset_real.y - mag_offset_visual_obj.y) < 0.001
            )
            spacing_match = abs(mag_spacing_real - mag_spacing_visual) < 0.001
            split_match = abs(split_pos_real - split_pos_visual) < 0.001

            if not (offset_match and spacing_match and split_match):
                mag_offset_obj = mag_offset_real
                mag_spacing = mag_spacing_real
                split_pos = split_pos_real
            else:
                mag_offset_obj = mag_offset_visual_obj
                mag_spacing = mag_spacing_visual
                split_pos = split_pos_visual

        mag_offset_visual = (mag_offset_obj.x, mag_offset_obj.y)

        from core.constants import AppConstants

        main_interp = render.interpolation_method
        optimize_mag_mov = getattr(view, "optimize_magnifier_movement", True)
        magnifier_movement_interp = getattr(
            render, "magnifier_movement_interpolation_method", "BILINEAR"
        )
        laser_smoothing_interp = getattr(
            render, "laser_smoothing_interpolation_method", "BILINEAR"
        )

        def resolve(option: str) -> str:
            main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_interp, 999)
            option_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(option, 999)
            return main_interp if main_speed <= option_speed else option

        eff_mag_mov = (
            resolve(magnifier_movement_interp) if optimize_mag_mov else main_interp
        )
        eff_laser = resolve(laser_smoothing_interp)

        params.update(
            {
                "split_pos": split_pos,
                "magnifier_pos": mag_pos,
                "magnifier_offset_relative_visual": mag_offset_visual,
                "magnifier_spacing_relative_visual": mag_spacing,
                "magnifier_size_relative": view.magnifier_size_relative,
                "capture_size_relative": view.capture_size_relative,
                "is_horizontal": view.is_horizontal,
                "magnifier_is_horizontal": view.magnifier_is_horizontal,
                "magnifier_internal_split": view.magnifier_internal_split,
                "use_magnifier": view.use_magnifier,
                "magnifier_visible_left": view.magnifier_visible_left,
                "magnifier_visible_center": view.magnifier_visible_center,
                "magnifier_visible_right": view.magnifier_visible_right,
                "is_magnifier_combined": view.is_magnifier_combined,
                "diff_mode": view.diff_mode,
                "channel_view_mode": view.channel_view_mode,
                "is_interactive_mode": interaction.is_interactive_mode,
                "highlighted_magnifier_element": view.highlighted_magnifier_element,
                "movement_interpolation_method": eff_mag_mov,
                "magnifier_movement_interpolation_method": eff_mag_mov,
                "laser_smoothing_interpolation_method": eff_laser,
            }
        )
        return params
