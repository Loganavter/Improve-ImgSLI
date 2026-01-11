import logging
import uuid
import copy
from collections import OrderedDict
from dataclasses import dataclass, field, asdict, replace
from typing import Optional, Any, List, Dict, Set
from PyQt6.QtCore import QObject, pyqtSignal, QPointF, QPoint, QRect, QByteArray
from PyQt6.QtGui import QColor

logger = logging.getLogger("ImproveImgSLI")

def safe_color_copy(c: QColor) -> QColor:
    return QColor(c.red(), c.green(), c.blue(), c.alpha())

def safe_pointf_copy(p: Optional[QPointF]) -> Optional[QPointF]:
    if p is None: return None
    return QPointF(p.x(), p.y())

@dataclass
class ImageItem:
    image: Optional[Any] = None
    path: str = ""
    display_name: str = ""
    rating: int = 0

@dataclass
class DocumentModel:
    image_list1: List[ImageItem] = field(default_factory=list)
    image_list2: List[ImageItem] = field(default_factory=list)
    current_index1: int = -1
    current_index2: int = -1
    original_image1: Optional[Any] = None
    original_image2: Optional[Any] = None
    full_res_image1: Optional[Any] = None
    full_res_image2: Optional[Any] = None
    image1_path: Optional[str] = None
    image2_path: Optional[str] = None
    preview_image1: Optional[Any] = None
    preview_image2: Optional[Any] = None
    full_res_ready1: bool = False
    full_res_ready2: bool = False
    preview_ready1: bool = False
    preview_ready2: bool = False
    progressive_load_in_progress1: bool = False
    progressive_load_in_progress2: bool = False

    def get_current_display_name(self, slot: int) -> str:
        idx = self.current_index1 if slot == 1 else self.current_index2
        lst = self.image_list1 if slot == 1 else self.image_list2
        if 0 <= idx < len(lst):
            return lst[idx].display_name
        return ""

@dataclass
class MagnifierModel:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    visible: bool = True
    position: QPointF = field(default_factory=lambda: QPointF(0.5, 0.5))
    size_relative: float = 0.2
    capture_size_relative: float = 0.1

    border_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 230))
    divider_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 230))
    laser_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 120))
    capture_ring_color: QColor = field(default_factory=lambda: QColor(255, 50, 100, 230))

    offset_relative: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
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
    frozen_position: Optional[QPointF] = None
    show_capture_area: bool = True
    interpolation_method: str = "BILINEAR"

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.position = safe_pointf_copy(self.position)
        new_obj.border_color = safe_color_copy(self.border_color)
        new_obj.divider_color = safe_color_copy(self.divider_color)
        new_obj.laser_color = safe_color_copy(self.laser_color)
        new_obj.capture_ring_color = safe_color_copy(self.capture_ring_color)
        new_obj.offset_relative = safe_pointf_copy(self.offset_relative)
        new_obj.frozen_position = safe_pointf_copy(self.frozen_position)
        return new_obj

@dataclass
class RenderConfig:
    divider_line_visible: bool = True
    divider_line_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    divider_line_thickness: int = 3

    magnifier_divider_visible: bool = True
    magnifier_divider_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 230))
    magnifier_divider_thickness: int = 2

    magnifier_border_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 230))
    magnifier_laser_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    capture_ring_color: QColor = field(default_factory=lambda: QColor(255, 50, 100, 230))
    show_magnifier_guides: bool = False
    magnifier_guides_thickness: int = 1

    interpolation_method: str = "BILINEAR"
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
    file_name_color: QColor = field(default_factory=lambda: QColor(255, 0, 0, 255))
    file_name_bg_color: QColor = field(default_factory=lambda: QColor(0, 0, 0, 80))
    draw_text_background: bool = True
    text_placement_mode: str = "edges"
    max_name_length: int = 50

    show_capture_area_on_main_image: bool = True

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.divider_line_color = safe_color_copy(self.divider_line_color)
        new_obj.magnifier_divider_color = safe_color_copy(self.magnifier_divider_color)
        new_obj.magnifier_border_color = safe_color_copy(self.magnifier_border_color)
        new_obj.magnifier_laser_color = safe_color_copy(self.magnifier_laser_color)
        new_obj.capture_ring_color = safe_color_copy(self.capture_ring_color)
        new_obj.file_name_color = safe_color_copy(self.file_name_color)
        new_obj.file_name_bg_color = safe_color_copy(self.file_name_bg_color)
        return new_obj

    def to_dict(self) -> dict:
        return {
            'divider_line_visible': self.divider_line_visible,
            'divider_line_color': (self.divider_line_color.red(), self.divider_line_color.green(), self.divider_line_color.blue(), self.divider_line_color.alpha()),
            'divider_line_thickness': self.divider_line_thickness,
            'magnifier_divider_visible': self.magnifier_divider_visible,
            'magnifier_divider_color': (self.magnifier_divider_color.red(), self.magnifier_divider_color.green(), self.magnifier_divider_color.blue(), self.magnifier_divider_color.alpha()),
            'magnifier_divider_thickness': self.magnifier_divider_thickness,
            'magnifier_border_color': (self.magnifier_border_color.red(), self.magnifier_border_color.green(), self.magnifier_border_color.blue(), self.magnifier_border_color.alpha()),
            'magnifier_laser_color': (self.magnifier_laser_color.red(), self.magnifier_laser_color.green(), self.magnifier_laser_color.blue(), self.magnifier_laser_color.alpha()),
            'capture_ring_color': (self.capture_ring_color.red(), self.capture_ring_color.green(), self.capture_ring_color.blue(), self.capture_ring_color.alpha()),
            'show_magnifier_guides': self.show_magnifier_guides,
            'magnifier_guides_thickness': self.magnifier_guides_thickness,
            'interpolation_method': self.interpolation_method,
            'movement_interpolation_method': self.movement_interpolation_method,
            'magnifier_movement_interpolation_method': self.magnifier_movement_interpolation_method,
            'laser_smoothing_interpolation_method': self.laser_smoothing_interpolation_method,
            'optimize_laser_smoothing': self.optimize_laser_smoothing,
            'display_resolution_limit': self.display_resolution_limit,
            'jpeg_quality': self.jpeg_quality,
            'include_file_names_in_saved': self.include_file_names_in_saved,
            'font_size_percent': self.font_size_percent,
            'font_weight': self.font_weight,
            'text_alpha_percent': self.text_alpha_percent,
            'file_name_color': (self.file_name_color.red(), self.file_name_color.green(), self.file_name_color.blue(), self.file_name_color.alpha()),
            'file_name_bg_color': (self.file_name_bg_color.red(), self.file_name_bg_color.green(), self.file_name_bg_color.blue(), self.file_name_bg_color.alpha()),
            'draw_text_background': self.draw_text_background,
            'text_placement_mode': self.text_placement_mode,
            'max_name_length': self.max_name_length,
            'show_capture_area_on_main_image': self.show_capture_area_on_main_image,
        }

@dataclass
class SessionData:
    image1: Optional[Any] = None
    image2: Optional[Any] = None

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

    loaded_image1_paths: List[str] = field(default_factory=list)
    loaded_image2_paths: List[str] = field(default_factory=list)
    loaded_current_index1: int = -1
    loaded_current_index2: int = -1

    auto_calculate_psnr: bool = False
    auto_calculate_ssim: bool = False
    psnr_value: Optional[float] = None
    ssim_value: Optional[float] = None

@dataclass
class ViewState:
    split_position: float = 0.5
    split_position_visual: float = 0.5
    is_horizontal: bool = False

    diff_mode: str = 'off'
    channel_view_mode: str = 'RGB'

    use_magnifier: bool = False
    magnifiers: Dict[str, MagnifierModel] = field(default_factory=dict)
    active_magnifier_id: Optional[str] = None
    magnifier_size_relative: float = 0.2
    capture_size_relative: float = 0.1
    capture_position_relative: QPointF = field(default_factory=lambda: QPointF(0.5, 0.5))
    freeze_magnifier: bool = False
    frozen_capture_point_relative: Optional[QPointF] = None
    magnifier_offset_relative: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
    magnifier_spacing_relative: float = 0.05
    magnifier_offset_relative_visual: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
    magnifier_spacing_relative_visual: float = 0.05
    magnifier_is_horizontal: bool = False
    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    magnifier_internal_split: float = 0.5
    magnifier_screen_center: QPoint = field(default_factory=lambda: QPoint())
    magnifier_screen_size: int = 0
    is_magnifier_combined: bool = False
    optimize_magnifier_movement: bool = True

    pixmap_width: int = 0
    pixmap_height: int = 0
    image_display_rect_on_label: QRect = field(default_factory=lambda: QRect())
    fixed_label_width: Optional[int] = None
    fixed_label_height: Optional[int] = None
    resize_in_progress: bool = False

    is_interactive_mode: bool = False
    is_dragging_split_line: bool = False
    is_dragging_capture_point: bool = False
    is_dragging_split_in_magnifier: bool = False
    is_dragging_any_slider: bool = False
    pressed_keys: Set[int] = field(default_factory=set)
    space_bar_pressed: bool = False

    highlighted_magnifier_element: Optional[str] = None

    showing_single_image_mode: int = 0
    movement_speed_per_sec: float = 2.0
    text_bg_visual_height: float = 0.0
    text_bg_visual_width: float = 0.0

    loaded_geometry: QByteArray = field(default_factory=lambda: QByteArray())
    loaded_was_maximized: bool = False
    loaded_previous_geometry: QByteArray = field(default_factory=lambda: QByteArray())
    loaded_debug_mode_enabled: bool = False

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.magnifiers = {k: v.clone() for k, v in self.magnifiers.items()}
        new_obj.capture_position_relative = safe_pointf_copy(self.capture_position_relative)
        new_obj.frozen_capture_point_relative = safe_pointf_copy(self.frozen_capture_point_relative)
        new_obj.magnifier_offset_relative = safe_pointf_copy(self.magnifier_offset_relative)
        new_obj.magnifier_offset_relative_visual = safe_pointf_copy(self.magnifier_offset_relative_visual)
        new_obj.magnifier_screen_center = QPoint(self.magnifier_screen_center) if self.magnifier_screen_center else QPoint()
        new_obj.image_display_rect_on_label = QRect(self.image_display_rect_on_label) if self.image_display_rect_on_label else QRect()
        new_obj.pressed_keys = set(self.pressed_keys)
        new_obj.loaded_geometry = QByteArray(self.loaded_geometry)
        new_obj.loaded_previous_geometry = QByteArray(self.loaded_previous_geometry)
        return new_obj

class ViewportState:
    __slots__ = ('_render_config', '_session_data', '_view_state', '_viewport_plugin_state', '_analysis_plugin_state',
                 '_last_source1_id', '_last_source2_id', '_last_render_params')

    def __init__(self, render_config: Optional[RenderConfig] = None,
                 session_data: Optional[SessionData] = None,
                 view_state: Optional[ViewState] = None):
        self._render_config = render_config or RenderConfig()
        self._session_data = session_data or SessionData()
        self._view_state = view_state or ViewState()
        self._viewport_plugin_state = None
        self._analysis_plugin_state = None
        self._last_source1_id = 0
        self._last_source2_id = 0
        self._last_render_params = None

    @property
    def render_config(self) -> RenderConfig: return self._render_config

    @render_config.setter
    def render_config(self, val): self._render_config = val

    @property
    def session_data(self) -> SessionData: return self._session_data

    @session_data.setter
    def session_data(self, val): self._session_data = val

    @property
    def view_state(self) -> ViewState: return self._view_state

    @view_state.setter
    def view_state(self, val): self._view_state = val

    def set_viewport_plugin_state(self, state: Any):
        self._viewport_plugin_state = state

    def set_analysis_plugin_state(self, state: Any):
        self._analysis_plugin_state = state

    @property
    def split_position(self) -> float: return self._view_state.split_position
    @split_position.setter
    def split_position(self, val: float): self._view_state.split_position = val

    @property
    def split_position_visual(self) -> float: return self._view_state.split_position_visual
    @split_position_visual.setter
    def split_position_visual(self, val: float): self._view_state.split_position_visual = val

    @property
    def is_horizontal(self) -> bool: return self._view_state.is_horizontal
    @is_horizontal.setter
    def is_horizontal(self, val: bool): self._view_state.is_horizontal = val

    @property
    def use_magnifier(self) -> bool: return self._view_state.use_magnifier
    @use_magnifier.setter
    def use_magnifier(self, val: bool): self._view_state.use_magnifier = val

    @property
    def active_magnifier_id(self) -> Optional[str]: return self._view_state.active_magnifier_id
    @active_magnifier_id.setter
    def active_magnifier_id(self, val: Optional[str]): self._view_state.active_magnifier_id = val

    @property
    def capture_position_relative(self) -> QPointF: return self._view_state.capture_position_relative
    @capture_position_relative.setter
    def capture_position_relative(self, val: QPointF): self._view_state.capture_position_relative = val

    @property
    def magnifier_size_relative(self) -> float: return self._view_state.magnifier_size_relative
    @magnifier_size_relative.setter
    def magnifier_size_relative(self, val: float): self._view_state.magnifier_size_relative = val

    @property
    def capture_size_relative(self) -> float: return self._view_state.capture_size_relative
    @capture_size_relative.setter
    def capture_size_relative(self, val: float): self._view_state.capture_size_relative = val

    @property
    def movement_speed_per_sec(self) -> float: return self._view_state.movement_speed_per_sec
    @movement_speed_per_sec.setter
    def movement_speed_per_sec(self, val: float): self._view_state.movement_speed_per_sec = val

    @property
    def freeze_magnifier(self) -> bool: return self._view_state.freeze_magnifier
    @freeze_magnifier.setter
    def freeze_magnifier(self, val: bool): self._view_state.freeze_magnifier = val

    @property
    def frozen_capture_point_relative(self) -> Optional[QPointF]: return self._view_state.frozen_capture_point_relative
    @frozen_capture_point_relative.setter
    def frozen_capture_point_relative(self, val: Optional[QPointF]): self._view_state.frozen_capture_point_relative = val

    @property
    def magnifier_offset_relative(self) -> QPointF: return self._view_state.magnifier_offset_relative
    @magnifier_offset_relative.setter
    def magnifier_offset_relative(self, val: QPointF): self._view_state.magnifier_offset_relative = val

    @property
    def magnifier_offset_relative_visual(self) -> QPointF: return self._view_state.magnifier_offset_relative_visual
    @magnifier_offset_relative_visual.setter
    def magnifier_offset_relative_visual(self, val: QPointF): self._view_state.magnifier_offset_relative_visual = val

    @property
    def magnifier_spacing_relative(self) -> float: return self._view_state.magnifier_spacing_relative
    @magnifier_spacing_relative.setter
    def magnifier_spacing_relative(self, val: float): self._view_state.magnifier_spacing_relative = val

    @property
    def magnifier_spacing_relative_visual(self) -> float: return self._view_state.magnifier_spacing_relative_visual
    @magnifier_spacing_relative_visual.setter
    def magnifier_spacing_relative_visual(self, val: float): self._view_state.magnifier_spacing_relative_visual = val

    @property
    def is_interactive_mode(self) -> bool: return self._view_state.is_interactive_mode
    @is_interactive_mode.setter
    def is_interactive_mode(self, val: bool): self._view_state.is_interactive_mode = val

    @property
    def is_dragging_split_line(self) -> bool: return self._view_state.is_dragging_split_line
    @is_dragging_split_line.setter
    def is_dragging_split_line(self, val: bool): self._view_state.is_dragging_split_line = val

    @property
    def is_dragging_capture_point(self) -> bool: return self._view_state.is_dragging_capture_point
    @is_dragging_capture_point.setter
    def is_dragging_capture_point(self, val: bool): self._view_state.is_dragging_capture_point = val

    @property
    def is_dragging_split_in_magnifier(self) -> bool: return self._view_state.is_dragging_split_in_magnifier
    @is_dragging_split_in_magnifier.setter
    def is_dragging_split_in_magnifier(self, val: bool): self._view_state.is_dragging_split_in_magnifier = val

    @property
    def is_dragging_any_slider(self) -> bool: return self._view_state.is_dragging_any_slider
    @is_dragging_any_slider.setter
    def is_dragging_any_slider(self, val: bool): self._view_state.is_dragging_any_slider = val

    @property
    def pressed_keys(self) -> Set[int]: return self._view_state.pressed_keys
    @pressed_keys.setter
    def pressed_keys(self, val: Set[int]): self._view_state.pressed_keys = val

    @property
    def space_bar_pressed(self) -> bool: return self._view_state.space_bar_pressed
    @space_bar_pressed.setter
    def space_bar_pressed(self, val: bool): self._view_state.space_bar_pressed = val

    @property
    def image1(self) -> Optional[Any]: return self._session_data.image1
    @image1.setter
    def image1(self, val: Any): self._session_data.image1 = val

    @property
    def image2(self) -> Optional[Any]: return self._session_data.image2
    @image2.setter
    def image2(self, val: Any): self._session_data.image2 = val

    @property
    def display_cache_image1(self) -> Optional[Any]: return self._session_data.display_cache_image1
    @display_cache_image1.setter
    def display_cache_image1(self, val: Any): self._session_data.display_cache_image1 = val

    @property
    def display_cache_image2(self) -> Optional[Any]: return self._session_data.display_cache_image2
    @display_cache_image2.setter
    def display_cache_image2(self, val: Any): self._session_data.display_cache_image2 = val

    @property
    def scaled_image1_for_display(self) -> Optional[Any]: return self._session_data.scaled_image1_for_display
    @scaled_image1_for_display.setter
    def scaled_image1_for_display(self, val: Any): self._session_data.scaled_image1_for_display = val

    @property
    def scaled_image2_for_display(self) -> Optional[Any]: return self._session_data.scaled_image2_for_display
    @scaled_image2_for_display.setter
    def scaled_image2_for_display(self, val: Any): self._session_data.scaled_image2_for_display = val

    @property
    def cached_scaled_image_dims(self) -> Optional[tuple]: return self._session_data.cached_scaled_image_dims
    @cached_scaled_image_dims.setter
    def cached_scaled_image_dims(self, val: Optional[tuple]): self._session_data.cached_scaled_image_dims = val

    @property
    def last_display_cache_params(self) -> Optional[tuple]: return self._session_data.last_display_cache_params
    @last_display_cache_params.setter
    def last_display_cache_params(self, val: Optional[tuple]): self._session_data.last_display_cache_params = val

    @property
    def cached_diff_image(self) -> Optional[Any]: return self._session_data.cached_diff_image
    @cached_diff_image.setter
    def cached_diff_image(self, val: Any): self._session_data.cached_diff_image = val

    @property
    def loaded_image1_paths(self) -> List[str]: return self._session_data.loaded_image1_paths
    @loaded_image1_paths.setter
    def loaded_image1_paths(self, val: List[str]): self._session_data.loaded_image1_paths = val

    @property
    def loaded_image2_paths(self) -> List[str]: return self._session_data.loaded_image2_paths
    @loaded_image2_paths.setter
    def loaded_image2_paths(self, val: List[str]): self._session_data.loaded_image2_paths = val

    @property
    def loaded_current_index1(self) -> int: return self._session_data.loaded_current_index1
    @loaded_current_index1.setter
    def loaded_current_index1(self, val: int): self._session_data.loaded_current_index1 = val

    @property
    def loaded_current_index2(self) -> int: return self._session_data.loaded_current_index2
    @loaded_current_index2.setter
    def loaded_current_index2(self, val: int): self._session_data.loaded_current_index2 = val

    @property
    def auto_calculate_psnr(self) -> bool: return self._session_data.auto_calculate_psnr
    @auto_calculate_psnr.setter
    def auto_calculate_psnr(self, val: bool): self._session_data.auto_calculate_psnr = val

    @property
    def auto_calculate_ssim(self) -> bool: return self._session_data.auto_calculate_ssim
    @auto_calculate_ssim.setter
    def auto_calculate_ssim(self, val: bool): self._session_data.auto_calculate_ssim = val

    @property
    def psnr_value(self) -> Optional[float]: return self._session_data.psnr_value
    @psnr_value.setter
    def psnr_value(self, val: Optional[float]): self._session_data.psnr_value = val

    @property
    def ssim_value(self) -> Optional[float]: return self._session_data.ssim_value
    @ssim_value.setter
    def ssim_value(self, val: Optional[float]): self._session_data.ssim_value = val

    @property
    def unification_in_progress(self) -> bool: return self._session_data.unification_in_progress
    @unification_in_progress.setter
    def unification_in_progress(self, val: bool): self._session_data.unification_in_progress = val

    @property
    def pending_unification_paths(self) -> Optional[tuple]: return self._session_data.pending_unification_paths
    @pending_unification_paths.setter
    def pending_unification_paths(self, val: Optional[tuple]): self._session_data.pending_unification_paths = val

    @property
    def display_resolution_limit(self) -> int: return self._render_config.display_resolution_limit
    @display_resolution_limit.setter
    def display_resolution_limit(self, val: int): self._render_config.display_resolution_limit = val

    @property
    def interpolation_method(self) -> str: return self._render_config.interpolation_method
    @interpolation_method.setter
    def interpolation_method(self, val: str): self._render_config.interpolation_method = val

    @property
    def movement_interpolation_method(self) -> str: return self._render_config.movement_interpolation_method
    @movement_interpolation_method.setter
    def movement_interpolation_method(self, val: str): self._render_config.movement_interpolation_method = val

    @property
    def optimize_laser_smoothing(self) -> bool: return self._render_config.optimize_laser_smoothing
    @optimize_laser_smoothing.setter
    def optimize_laser_smoothing(self, val: bool): self._render_config.optimize_laser_smoothing = val

    @property
    def include_file_names_in_saved(self) -> bool: return self._render_config.include_file_names_in_saved
    @include_file_names_in_saved.setter
    def include_file_names_in_saved(self, val: bool): self._render_config.include_file_names_in_saved = val

    @property
    def font_size_percent(self) -> int: return self._render_config.font_size_percent
    @font_size_percent.setter
    def font_size_percent(self, val: int): self._render_config.font_size_percent = val

    @property
    def font_weight(self) -> int: return self._render_config.font_weight
    @font_weight.setter
    def font_weight(self, val: int): self._render_config.font_weight = val

    @property
    def text_alpha_percent(self) -> int: return self._render_config.text_alpha_percent
    @text_alpha_percent.setter
    def text_alpha_percent(self, val: int): self._render_config.text_alpha_percent = val

    @property
    def file_name_color(self) -> QColor: return self._render_config.file_name_color
    @file_name_color.setter
    def file_name_color(self, val: QColor): self._render_config.file_name_color = val

    @property
    def file_name_bg_color(self) -> QColor: return self._render_config.file_name_bg_color
    @file_name_bg_color.setter
    def file_name_bg_color(self, val: QColor): self._render_config.file_name_bg_color = val

    @property
    def draw_text_background(self) -> bool: return self._render_config.draw_text_background
    @draw_text_background.setter
    def draw_text_background(self, val: bool): self._render_config.draw_text_background = val

    @property
    def text_placement_mode(self) -> str: return self._render_config.text_placement_mode
    @text_placement_mode.setter
    def text_placement_mode(self, val: str): self._render_config.text_placement_mode = val

    @property
    def max_name_length(self) -> int: return self._render_config.max_name_length
    @max_name_length.setter
    def max_name_length(self, val: int): self._render_config.max_name_length = val

    @property
    def divider_line_visible(self) -> bool: return self._render_config.divider_line_visible
    @divider_line_visible.setter
    def divider_line_visible(self, val: bool): self._render_config.divider_line_visible = val

    @property
    def divider_line_color(self) -> QColor: return self._render_config.divider_line_color
    @divider_line_color.setter
    def divider_line_color(self, val: QColor): self._render_config.divider_line_color = val

    @property
    def divider_line_thickness(self) -> int: return self._render_config.divider_line_thickness
    @divider_line_thickness.setter
    def divider_line_thickness(self, val: int): self._render_config.divider_line_thickness = val

    @property
    def magnifier_divider_visible(self) -> bool: return self._render_config.magnifier_divider_visible
    @magnifier_divider_visible.setter
    def magnifier_divider_visible(self, val: bool): self._render_config.magnifier_divider_visible = val

    @property
    def magnifier_divider_color(self) -> QColor: return self._render_config.magnifier_divider_color
    @magnifier_divider_color.setter
    def magnifier_divider_color(self, val: QColor): self._render_config.magnifier_divider_color = val

    @property
    def magnifier_divider_thickness(self) -> int: return self._render_config.magnifier_divider_thickness
    @magnifier_divider_thickness.setter
    def magnifier_divider_thickness(self, val: int): self._render_config.magnifier_divider_thickness = val

    @property
    def magnifier_border_color(self) -> QColor: return self._render_config.magnifier_border_color
    @magnifier_border_color.setter
    def magnifier_border_color(self, val: QColor): self._render_config.magnifier_border_color = val

    @property
    def magnifier_laser_color(self) -> QColor: return self._render_config.magnifier_laser_color
    @magnifier_laser_color.setter
    def magnifier_laser_color(self, val: QColor): self._render_config.magnifier_laser_color = val

    @property
    def capture_ring_color(self) -> QColor: return self._render_config.capture_ring_color
    @capture_ring_color.setter
    def capture_ring_color(self, val: QColor): self._render_config.capture_ring_color = val

    @property
    def show_magnifier_guides(self) -> bool: return self._render_config.show_magnifier_guides
    @show_magnifier_guides.setter
    def show_magnifier_guides(self, val: bool): self._render_config.show_magnifier_guides = val

    @property
    def magnifier_guides_thickness(self) -> int: return self._render_config.magnifier_guides_thickness
    @magnifier_guides_thickness.setter
    def magnifier_guides_thickness(self, val: int): self._render_config.magnifier_guides_thickness = val

    @property
    def diff_mode(self) -> str: return self._view_state.diff_mode
    @diff_mode.setter
    def diff_mode(self, val: str): self._view_state.diff_mode = val

    @property
    def channel_view_mode(self) -> str: return self._view_state.channel_view_mode
    @channel_view_mode.setter
    def channel_view_mode(self, val: str): self._view_state.channel_view_mode = val

    @property
    def magnifier_visible_left(self) -> bool: return self._view_state.magnifier_visible_left
    @magnifier_visible_left.setter
    def magnifier_visible_left(self, val: bool): self._view_state.magnifier_visible_left = val

    @property
    def magnifier_visible_center(self) -> bool: return self._view_state.magnifier_visible_center
    @magnifier_visible_center.setter
    def magnifier_visible_center(self, val: bool): self._view_state.magnifier_visible_center = val

    @property
    def magnifier_visible_right(self) -> bool: return self._view_state.magnifier_visible_right
    @magnifier_visible_right.setter
    def magnifier_visible_right(self, val: bool): self._view_state.magnifier_visible_right = val

    @property
    def magnifier_internal_split(self) -> float: return self._view_state.magnifier_internal_split
    @magnifier_internal_split.setter
    def magnifier_internal_split(self, val: float): self._view_state.magnifier_internal_split = val

    @property
    def magnifier_is_horizontal(self) -> bool: return self._view_state.magnifier_is_horizontal
    @magnifier_is_horizontal.setter
    def magnifier_is_horizontal(self, val: bool): self._view_state.magnifier_is_horizontal = val

    @property
    def is_magnifier_combined(self) -> bool: return self._view_state.is_magnifier_combined
    @is_magnifier_combined.setter
    def is_magnifier_combined(self, val: bool): self._view_state.is_magnifier_combined = val

    @property
    def optimize_magnifier_movement(self) -> bool: return self._view_state.optimize_magnifier_movement
    @optimize_magnifier_movement.setter
    def optimize_magnifier_movement(self, val: bool): self._view_state.optimize_magnifier_movement = val

    @property
    def highlighted_magnifier_element(self) -> Optional[str]: return self._view_state.highlighted_magnifier_element
    @highlighted_magnifier_element.setter
    def highlighted_magnifier_element(self, val: Optional[str]): self._view_state.highlighted_magnifier_element = val

    @property
    def resize_in_progress(self) -> bool: return self._view_state.resize_in_progress
    @resize_in_progress.setter
    def resize_in_progress(self, val: bool): self._view_state.resize_in_progress = val

    @property
    def pixmap_width(self) -> int: return self._view_state.pixmap_width
    @pixmap_width.setter
    def pixmap_width(self, val: int): self._view_state.pixmap_width = val

    @property
    def pixmap_height(self) -> int: return self._view_state.pixmap_height
    @pixmap_height.setter
    def pixmap_height(self, val: int): self._view_state.pixmap_height = val

    @property
    def image_display_rect_on_label(self) -> QRect: return self._view_state.image_display_rect_on_label
    @image_display_rect_on_label.setter
    def image_display_rect_on_label(self, val: QRect): self._view_state.image_display_rect_on_label = val

    @property
    def fixed_label_width(self) -> Optional[int]: return self._view_state.fixed_label_width
    @fixed_label_width.setter
    def fixed_label_width(self, val: Optional[int]): self._view_state.fixed_label_width = val

    @property
    def fixed_label_height(self) -> Optional[int]: return self._view_state.fixed_label_height
    @fixed_label_height.setter
    def fixed_label_height(self, val: Optional[int]): self._view_state.fixed_label_height = val

    @property
    def showing_single_image_mode(self) -> int: return self._view_state.showing_single_image_mode
    @showing_single_image_mode.setter
    def showing_single_image_mode(self, val: int): self._view_state.showing_single_image_mode = val

    @property
    def text_bg_visual_height(self) -> float: return self._view_state.text_bg_visual_height
    @text_bg_visual_height.setter
    def text_bg_visual_height(self, val: float): self._view_state.text_bg_visual_height = val

    @property
    def text_bg_visual_width(self) -> float: return self._view_state.text_bg_visual_width
    @text_bg_visual_width.setter
    def text_bg_visual_width(self, val: float): self._view_state.text_bg_visual_width = val

    @property
    def magnifier_screen_center(self) -> QPoint: return self._view_state.magnifier_screen_center
    @magnifier_screen_center.setter
    def magnifier_screen_center(self, val: QPoint): self._view_state.magnifier_screen_center = val

    @property
    def magnifier_screen_size(self) -> int: return self._view_state.magnifier_screen_size
    @magnifier_screen_size.setter
    def magnifier_screen_size(self, val: int): self._view_state.magnifier_screen_size = val

    @property
    def loaded_geometry(self) -> QByteArray: return self._view_state.loaded_geometry
    @loaded_geometry.setter
    def loaded_geometry(self, val: QByteArray): self._view_state.loaded_geometry = val

    @property
    def loaded_was_maximized(self) -> bool: return self._view_state.loaded_was_maximized
    @loaded_was_maximized.setter
    def loaded_was_maximized(self, val: bool): self._view_state.loaded_was_maximized = val

    @property
    def loaded_previous_geometry(self) -> QByteArray: return self._view_state.loaded_previous_geometry
    @loaded_previous_geometry.setter
    def loaded_previous_geometry(self, val: QByteArray): self._view_state.loaded_previous_geometry = val

    @property
    def loaded_debug_mode_enabled(self) -> bool: return self._view_state.loaded_debug_mode_enabled
    @loaded_debug_mode_enabled.setter
    def loaded_debug_mode_enabled(self, val: bool): self._view_state.loaded_debug_mode_enabled = val

    def __getattr__(self, name: str):

        try:
            _view_state = object.__getattribute__(self, '_view_state')
            _session_data = object.__getattribute__(self, '_session_data')
            _render_config = object.__getattribute__(self, '_render_config')
            _viewport_plugin_state = object.__getattribute__(self, '_viewport_plugin_state')
            _analysis_plugin_state = object.__getattribute__(self, '_analysis_plugin_state')
        except AttributeError:
            raise AttributeError(f"'ViewportState' object has no attribute '{name}'")

        _sentinel = object()
        val = getattr(_view_state, name, _sentinel)
        if val is not _sentinel:
            return val
        val = getattr(_session_data, name, _sentinel)
        if val is not _sentinel:
            return val
        val = getattr(_render_config, name, _sentinel)
        if val is not _sentinel:
            return val
        if _viewport_plugin_state:
            val = getattr(_viewport_plugin_state, name, _sentinel)
            if val is not _sentinel:
                return val
        if _analysis_plugin_state:
            val = getattr(_analysis_plugin_state, name, _sentinel)
            if val is not _sentinel:
                return val
        raise AttributeError(f"'ViewportState' object has no attribute '{name}'")

    def clone(self):

        new_obj = ViewportState(
            render_config=self._render_config.clone(),
            session_data=SessionData(),
            view_state=self._view_state.clone()
        )
        new_obj._viewport_plugin_state = self._viewport_plugin_state
        new_obj._analysis_plugin_state = self._analysis_plugin_state
        new_obj._last_source1_id = self._last_source1_id
        new_obj._last_source2_id = self._last_source2_id
        new_obj._last_render_params = self._last_render_params
        return new_obj

    def clone_visual_state(self):
        return self.clone()

    def freeze_for_export(self):
        frozen = self.clone()
        frozen.view_state.showing_single_image_mode = 0
        frozen.view_state.space_bar_pressed = False
        frozen.view_state.pressed_keys = set()
        frozen.view_state.is_dragging_split_line = False
        frozen.view_state.is_dragging_capture_point = False
        frozen.view_state.is_dragging_split_in_magnifier = False
        frozen.view_state.is_dragging_any_slider = False
        return frozen

    def get_render_params(self) -> dict:

        d = self._render_config.to_dict()

        view = self._view_state
        render = self._render_config
        capture_pos = view.capture_position_relative
        mag_pos = (capture_pos.x(), capture_pos.y()) if capture_pos else (0.5, 0.5)

        is_interactive = view.is_interactive_mode

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
            offset_match = False
            if mag_offset_real and mag_offset_visual_obj:
                offset_match = (
                    abs(mag_offset_real.x() - mag_offset_visual_obj.x()) < 0.001 and
                    abs(mag_offset_real.y() - mag_offset_visual_obj.y()) < 0.001
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

        mag_offset_visual = (mag_offset_obj.x(), mag_offset_obj.y()) if mag_offset_obj else None

        from core.constants import AppConstants
        main_interp = render.interpolation_method
        magnifier_movement_interp = getattr(render, 'magnifier_movement_interpolation_method', 'BILINEAR')
        laser_smoothing_interp = getattr(render, 'laser_smoothing_interpolation_method', 'BILINEAR')

        def resolve(opt):
            m_s = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_interp, 999)
            o_s = AppConstants.INTERPOLATION_SPEED_ORDER.get(opt, 999)
            return main_interp if m_s <= o_s else opt

        eff_mag_mov = resolve(magnifier_movement_interp)
        eff_laser = resolve(laser_smoothing_interp)

        d.update({
            'split_pos': split_pos,
            'magnifier_pos': mag_pos,
            'magnifier_offset_relative_visual': mag_offset_visual,
            'magnifier_spacing_relative_visual': mag_spacing,
            'magnifier_size_relative': view.magnifier_size_relative,
            'capture_size_relative': view.capture_size_relative,
            'is_horizontal': view.is_horizontal,
            'magnifier_is_horizontal': view.magnifier_is_horizontal,
            'magnifier_internal_split': view.magnifier_internal_split,
            'use_magnifier': view.use_magnifier,
            'magnifier_visible_left': view.magnifier_visible_left,
            'magnifier_visible_center': view.magnifier_visible_center,
            'magnifier_visible_right': view.magnifier_visible_right,
            'is_magnifier_combined': view.is_magnifier_combined,
            'diff_mode': view.diff_mode,
            'channel_view_mode': view.channel_view_mode,
            'is_interactive_mode': view.is_interactive_mode,
            'highlighted_magnifier_element': view.highlighted_magnifier_element,
            'movement_interpolation_method': eff_mag_mov,
            'magnifier_movement_interpolation_method': eff_mag_mov,
            'laser_smoothing_interpolation_method': eff_laser,
        })
        return d

@dataclass
class SettingsState:
    current_language: str = "en"
    theme: str = "auto"
    ui_font_mode: str = "builtin"
    ui_font_family: str = ""
    ui_mode: str = "beginner"
    debug_mode_enabled: bool = True
    system_notifications_enabled: bool = True
    auto_crop_black_borders: bool = True
    video_recording_fps: int = 60

    export_use_default_dir: bool = True
    export_default_dir: Optional[str] = None
    export_favorite_dir: Optional[str] = None
    export_video_favorite_dir: Optional[str] = None
    export_last_format: str = "PNG"
    export_quality: int = 95
    export_fill_background: bool = False
    export_background_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    export_last_filename: str = ""
    export_png_compress_level: int = 9
    export_comment_text: str = ""
    export_comment_keep_default: bool = False

    window_width: int = 1024
    window_height: int = 768
    window_x: int = 100
    window_y: int = 100
    window_was_maximized: bool = False

    def freeze_for_export(self):
        frozen = copy.copy(self)
        frozen.export_background_color = safe_color_copy(self.export_background_color)
        return frozen

class WorkerStoreSnapshot:
    def __init__(self, viewport, settings, document):
        self.viewport = viewport
        self.settings = settings
        self.document = document

class Store(QObject):
    state_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.document = DocumentModel()
        self.viewport = ViewportState()
        self.settings = SettingsState()
        self.recorder = None
        self._dispatcher = None

    def set_dispatcher(self, dispatcher):
        self._dispatcher = dispatcher
        if dispatcher:
            dispatcher.state_changed.connect(self.state_changed.emit)

    def get_dispatcher(self):
        return self._dispatcher

    def set_recorder(self, recorder):
        self.recorder = recorder

    def clear_all_caches(self):
        if self._dispatcher:
            from core.state_management.actions import ClearAllCachesAction
            self._dispatcher.dispatch(ClearAllCachesAction(), scope="viewport")
        else:

            self.viewport.session_data.unified_image_cache.clear()
            self.invalidate_geometry_cache()

    def invalidate_render_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateRenderCacheAction
            self._dispatcher.dispatch(InvalidateRenderCacheAction(), scope="viewport")
        else:
            session = self.viewport.session_data
            session.caches.clear()
            session.magnifier_cache.clear()
            session.cached_split_base_image = None
            session.last_split_cached_params = None

    def invalidate_geometry_cache(self):
        if self._dispatcher:
            from core.state_management.actions import InvalidateGeometryCacheAction
            self._dispatcher.dispatch(InvalidateGeometryCacheAction(), scope="viewport")
        else:
            session = self.viewport.session_data
            session.scaled_image1_for_display = None
            session.scaled_image2_for_display = None
            session.cached_scaled_image_dims = None
            session.display_cache_image1 = None
            session.display_cache_image2 = None
            session.last_display_cache_params = None
            self.invalidate_render_cache()

    def clear_interactive_caches(self):
        self.invalidate_render_cache()

    def clear_image_slot_data(self, image_number: int):
        if self._dispatcher:
            from core.state_management.actions import ClearImageSlotDataAction
            self._dispatcher.dispatch(ClearImageSlotDataAction(image_number), scope="viewport")
        else:
            if image_number == 1:
                self.document.original_image1 = None
                self.document.full_res_image1 = None
                self.document.preview_image1 = None
                self.document.image1_path = None
                self.viewport.image1 = None
                self.viewport.display_cache_image1 = None
            else:
                self.document.original_image2 = None
                self.document.full_res_image2 = None
                self.document.preview_image2 = None
                self.document.image2_path = None
                self.viewport.image2 = None
                self.viewport.display_cache_image2 = None

            session = self.viewport.session_data
            session.scaled_image1_for_display = None
            session.scaled_image2_for_display = None
            session.cached_scaled_image_dims = None
            session.last_display_cache_params = None
            self.invalidate_render_cache()

    def emit_state_change(self, scope: str = "viewport"):
        self.state_changed.emit(scope)

    def set_current_image_data(self, image_number: int, image, path, display_name):

        if self._dispatcher:
            from core.state_management.actions import SetFullResImageAction, SetImagePathAction, SetOriginalImageAction

            self._dispatcher.dispatch(SetFullResImageAction(image_number, image), scope="document")
            self._dispatcher.dispatch(SetOriginalImageAction(image_number, image), scope="document")
            self._dispatcher.dispatch(SetImagePathAction(image_number, path), scope="document")
        else:
            if image_number == 1:
                self.document.full_res_image1 = image
                self.document.original_image1 = image
                self.document.image1_path = path
                self.viewport.image1 = image
            else:
                self.document.full_res_image2 = image
                self.document.original_image2 = image
                self.document.image2_path = path
                self.viewport.image2 = image
            self.emit_state_change("document")

    def swap_all_image_data(self):

        doc = self.document
        vp = self.viewport

        doc.image_list1, doc.image_list2 = doc.image_list2, doc.image_list1
        doc.current_index1, doc.current_index2 = doc.current_index2, doc.current_index1

        doc.original_image1, doc.original_image2 = doc.original_image2, doc.original_image1
        doc.full_res_image1, doc.full_res_image2 = doc.full_res_image2, doc.full_res_image1
        doc.preview_image1, doc.preview_image2 = doc.preview_image2, doc.preview_image1
        doc.image1_path, doc.image2_path = doc.image2_path, doc.image1_path

        vp.image1, vp.image2 = vp.image2, vp.image1
        vp.display_cache_image1, vp.display_cache_image2 = vp.display_cache_image2, vp.display_cache_image1
        vp.scaled_image1_for_display, vp.scaled_image2_for_display = vp.scaled_image2_for_display, vp.scaled_image1_for_display

        self.invalidate_geometry_cache()
        self.emit_state_change("document")

    def copy_for_worker(self):

        src_render = self.viewport.render_config
        new_render_config = src_render.clone()

        src_view = self.viewport.view_state
        new_view_state = src_view.clone()

        new_view_state.split_position = src_view.split_position_visual
        new_view_state.magnifier_offset_relative = QPointF(src_view.magnifier_offset_relative_visual)
        new_view_state.magnifier_spacing_relative = src_view.magnifier_spacing_relative_visual

        src_session = self.viewport.session_data
        new_session_data = SessionData()

        new_session_data.loaded_image1_paths = list(src_session.loaded_image1_paths)
        new_session_data.loaded_image2_paths = list(src_session.loaded_image2_paths)

        new_viewport = ViewportState(new_render_config, new_session_data, new_view_state)

        new_doc = DocumentModel()
        new_doc.current_index1 = self.document.current_index1
        new_doc.current_index2 = self.document.current_index2
        new_doc.image_list1 = list(self.document.image_list1)
        new_doc.image_list2 = list(self.document.image_list2)
        new_doc.full_res_image1 = self.document.full_res_image1
        new_doc.full_res_image2 = self.document.full_res_image2
        new_doc.original_image1 = self.document.original_image1
        new_doc.original_image2 = self.document.original_image2

        return WorkerStoreSnapshot(new_viewport, self.settings.freeze_for_export(), new_doc)
