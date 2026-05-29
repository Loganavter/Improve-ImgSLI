from __future__ import annotations

import copy
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Set

from domain.types import Color, Point, Rect

logger = logging.getLogger("ImproveImgSLI")

@dataclass
class RenderConfig:
    interpolation_method: str = "BILINEAR"
    zoom_interpolation_method: str = "BILINEAR"
    movement_interpolation_method: str = "BILINEAR"
    interactive_movement_interpolation_method: str = "BILINEAR"
    display_resolution_limit: int = 0
    jpeg_quality: int = 95

    include_file_names_in_saved: bool = False
    font_size_percent: int = 120
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
            "interactive_movement_interpolation_method": self.interactive_movement_interpolation_method,
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
    feature_caches: dict = field(default_factory=dict)
    cached_split_base_image: Optional[Any] = None
    last_split_cached_params: Optional[tuple] = None
    cached_diff_image: Optional[Any] = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.unified_image_cache = self.unified_image_cache.__class__(
            self.unified_image_cache
        )
        new_obj.caches = dict(self.caches)
        new_obj.feature_caches = dict(self.feature_caches)
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

    active_overlay_screen_center: Point = field(default_factory=lambda: Point())
    active_overlay_screen_size: int = 0

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
    is_dragging_overlay_handle: bool = False
    is_dragging_overlay_split: bool = False
    is_dragging_any_slider: bool = False
    interaction_session_id: int = 0
    is_user_interacting: bool = False
    pressed_keys: Set[int] = field(default_factory=set)
    last_horizontal_movement_key: int | None = None
    last_vertical_movement_key: int | None = None
    last_spacing_movement_key: int | None = None
    space_bar_pressed: bool = False
    interactive_offset_relative_visual: Point = field(
        default_factory=lambda: Point(0.0, 0.0)
    )
    interactive_spacing_relative_visual: float = 0.1
    interactive_internal_split_visual: float = 0.5

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
    optimize_interactive_movement: bool = True
    overlay_enabled: bool = False

    highlighted_overlay_element: Optional[str] = None

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
        return new_obj

    def clone_visual_state(self):
        return self.clone()

    def freeze_for_export(self):
        frozen = self.clone()
        frozen.interaction_state.space_bar_pressed = False
        frozen.interaction_state.pressed_keys = set()
        frozen.interaction_state.is_dragging_split_line = False
        frozen.interaction_state.is_dragging_overlay_handle = False
        frozen.interaction_state.is_dragging_overlay_split = False
        frozen.interaction_state.is_dragging_any_slider = False
        frozen.interaction_state.is_interactive_mode = False
        frozen.interaction_state.is_user_interacting = False
        return frozen
