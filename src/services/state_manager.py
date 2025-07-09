import os
from PyQt6.QtCore import QObject, QPointF, QByteArray, QRect, pyqtSignal, QPoint
from PyQt6.QtGui import QColor
from PIL import Image
import os


class AppConstants:
    MIN_NAME_LENGTH_LIMIT = 10
    MAX_NAME_LENGTH_LIMIT = 150
    DEFAULT_MAGNIFIER_SIZE_RELATIVE = 0.4
    DEFAULT_CAPTURE_SIZE_RELATIVE = 0.1
    DEFAULT_CAPTURE_POS_RELATIVE = QPointF(0.5, 0.5)
    DEFAULT_MAGNIFIER_OFFSET_RELATIVE = QPointF(0.0, -0.15)
    DEFAULT_MAGNIFIER_SPACING_RELATIVE = 0.1
    DEFAULT_JPEG_QUALITY = 93
    DEFAULT_INTERPOLATION_METHOD = 'LANCZOS'
    BASE_MOVEMENT_SPEED = 0.5
    MIN_CHANGE_THRESHOLD = 0.0001
    SMOOTHING_FACTOR_POS = 0.15
    SMOOTHING_FACTOR_SPACING = 0.2
    SMOOTHING_FACTOR_SPLIT = 0.2
    LERP_STOP_THRESHOLD = 0.001
    MAX_TARGET_DELTA_PER_TICK = 0.1
    MIN_CAPTURE_THICKNESS = 1
    MAX_CAPTURE_THICKNESS = 4
    MIN_MAG_BORDER_THICKNESS = 1
    MAX_MAG_BORDER_THICKNESS = 4
    INTERPOLATION_METHODS_MAP = {
        'NEAREST': 'Nearest Neighbor',
        'BILINEAR': 'Bilinear',
        'BICUBIC': 'Bicubic',
        'LANCZOS': 'Lanczos'}


class AppState(QObject):
    stateChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._image_list1: list[tuple[Image.Image, str, str]] = []
        self._image_list2: list[tuple[Image.Image, str, str]] = []
        self._current_index1: int = -1
        self._current_index2: int = -1
        self._original_image1: Image.Image | None = None
        self._original_image2: Image.Image | None = None
        self._image1_path: str | None = None
        self._image2_path: str | None = None
        self._image1: Image.Image | None = None
        self._image2: Image.Image | None = None
        self._result_image: Image.Image | None = None
        self._split_position: float = 0.5
        self._split_position_visual: float = 0.5
        self._is_horizontal: bool = False
        self._use_magnifier: bool = False
        self._magnifier_size_relative: float = AppConstants.DEFAULT_MAGNIFIER_SIZE_RELATIVE
        self._capture_size_relative: float = AppConstants.DEFAULT_CAPTURE_SIZE_RELATIVE
        self._capture_position_relative: QPointF = AppConstants.DEFAULT_CAPTURE_POS_RELATIVE
        self._show_capture_area_on_main_image: bool = True
        self._freeze_magnifier: bool = False
        self._frozen_magnifier_absolute_pos: QPoint | None = None
        self._magnifier_offset_relative: QPointF = AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        self._magnifier_spacing_relative: float = AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        self._magnifier_offset_relative_visual: QPointF = QPointF(
            AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        self._magnifier_spacing_relative_visual: float = AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        self._interpolation_method: str = AppConstants.DEFAULT_INTERPOLATION_METHOD
        self._include_file_names_in_saved: bool = False
        self._font_size_percent: int = 100
        self._movement_speed_per_sec: float = 2.0
        self._max_name_length: int = 30
        self._file_name_color: QColor = QColor(255, 0, 0, 255)
        self._jpeg_quality: int = AppConstants.DEFAULT_JPEG_QUALITY
        self._current_language: str = 'en'
        self._pixmap_width: int = 0
        self._pixmap_height: int = 0
        self._image_display_rect_on_label = QRect()
        self._is_dragging_split_line: bool = False
        self._is_dragging_capture_point: bool = False
        self._is_dragging_any_slider: bool = False
        self._magnifier_is_actively_lerping: bool = False
        self._split_is_actively_lerping: bool = False
        self._magnifier_is_keyboard_panning: bool = False
        self._is_interactive_mode: bool = False
        self._resize_in_progress: bool = False
        self._pressed_keys: set[int] = set()
        self._space_bar_pressed: bool = False
        self._showing_single_image_mode: int = 0
        self._fixed_label_width: int | None = None
        self._fixed_label_height: int | None = None
        self.debug_mode_enabled: bool = False
        self.loaded_geometry: QByteArray = QByteArray()
        self.loaded_window_state: int = 0
        self.loaded_previous_geometry: QByteArray = QByteArray()
        self.loaded_image1_paths: list[str] = []
        self.loaded_image2_paths: list[str] = []
        self.loaded_current_index1: int = -1
        self.loaded_current_index2: int = -1
        self.loaded_language: str = 'en'
        self.loaded_max_name_length: int = 30
        self.loaded_movement_speed: float = 2.0
        self.loaded_filename_color_name: str = QColor(
            255, 0, 0, 255).name(QColor.NameFormat.HexArgb)
        self.loaded_jpeg_quality: int = AppConstants.DEFAULT_JPEG_QUALITY
        self.loaded_magnifier_size_relative: float = AppConstants.DEFAULT_MAGNIFIER_SIZE_RELATIVE
        self.loaded_capture_size_relative: float = AppConstants.DEFAULT_CAPTURE_SIZE_RELATIVE
        self.loaded_capture_pos_rel_x: float = AppConstants.DEFAULT_CAPTURE_POS_RELATIVE.x()
        self.loaded_capture_pos_rel_y: float = AppConstants.DEFAULT_CAPTURE_POS_RELATIVE.y()
        self.loaded_magnifier_offset_relative: QPointF = AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        self.loaded_magnifier_spacing_relative: float = AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        self.loaded_interpolation_method: str = AppConstants.DEFAULT_INTERPOLATION_METHOD
        self.loaded_file_names_state: bool = False
        self.loaded_debug_mode_enabled: bool = False
        self._cached_split_base_image: Image.Image | None = None
        self._last_split_cached_params: tuple | None = None
        self._magnifier_cache: dict = {}

    def clear_all_caches(self):
        self.clear_split_cache()
        self.clear_magnifier_cache()

    def clear_split_cache(self):
        self._cached_split_base_image = None
        self._last_split_cached_params = None

    def clear_magnifier_cache(self):
        self._magnifier_cache.clear()

    def copy_for_worker(self):
        new_state = AppState()

        new_state.split_position_visual = self.split_position_visual
        new_state.is_horizontal = self.is_horizontal
        new_state.use_magnifier = self.use_magnifier
        new_state.show_capture_area_on_main_image = self.show_capture_area_on_main_image
        new_state.capture_position_relative = QPointF(
            self.capture_position_relative)
        new_state.magnifier_offset_relative_visual = QPointF(
            self.magnifier_offset_relative_visual)
        new_state.magnifier_spacing_relative_visual = self.magnifier_spacing_relative_visual
        new_state.magnifier_size_relative = self.magnifier_size_relative
        new_state.capture_size_relative = self.capture_size_relative
        new_state.freeze_magnifier = self.freeze_magnifier
        if self.frozen_magnifier_absolute_pos:
            new_state.frozen_magnifier_absolute_pos = QPoint(
                self.frozen_magnifier_absolute_pos)
   
        new_state.include_file_names_in_saved = self.include_file_names_in_saved
        new_state.font_size_percent = self.font_size_percent
        new_state.max_name_length = self.max_name_length
        new_state.file_name_color = QColor(self.file_name_color)

        new_state.interpolation_method = self.interpolation_method
        new_state.is_interactive_mode = self.is_interactive_mode

        new_state._cached_split_base_image = self._cached_split_base_image
        new_state._last_split_cached_params = self._last_split_cached_params

        return new_state

    @property
    def fixed_label_width(self) -> int | None:
        return self._fixed_label_width

    @fixed_label_width.setter
    def fixed_label_width(self, value: int | None):
        self._fixed_label_width = value

    @property
    def fixed_label_height(self) -> int | None:
        return self._fixed_label_height

    @fixed_label_height.setter
    def fixed_label_height(self, value: int | None):
        self._fixed_label_height = value

    @property
    def current_language(self) -> str:
        return self._current_language

    @current_language.setter
    def current_language(self, value: str):
        if self._current_language != value:
            self._current_language = value
            self.stateChanged.emit()

    @property
    def image_list1(self) -> list[tuple[Image.Image, str, str]]:
        return self._image_list1

    @property
    def image_list2(self) -> list[tuple[Image.Image, str, str]]:
        return self._image_list2

    @property
    def current_index1(self) -> int:
        return self._current_index1

    @current_index1.setter
    def current_index1(self, value: int):
        if self._current_index1 != value:
            self._current_index1 = value
            self.stateChanged.emit()

    @property
    def current_index2(self) -> int:
        return self._current_index2

    @current_index2.setter
    def current_index2(self, value: int):
        if self._current_index2 != value:
            self._current_index2 = value
            self.stateChanged.emit()

    @property
    def original_image1(self) -> Image.Image | None:
        return self._original_image1

    @original_image1.setter
    def original_image1(self, value: Image.Image | None):
        self._original_image1 = value

    @property
    def original_image2(self) -> Image.Image | None:
        return self._original_image2

    @original_image2.setter
    def original_image2(self, value: Image.Image | None):
        self._original_image2 = value

    @property
    def image1(self) -> Image.Image | None:
        return self._image1

    @image1.setter
    def image1(self, value: Image.Image | None):
        self._image1 = value

    @property
    def image2(self) -> Image.Image | None:
        return self._image2

    @image2.setter
    def image2(self, value: Image.Image | None):
        self._image2 = value

    @property
    def result_image(self) -> Image.Image | None:
        return self._result_image

    @result_image.setter
    def result_image(self, value: Image.Image | None):
        self._result_image = value

    @property
    def is_horizontal(self) -> bool:
        return self._is_horizontal

    @is_horizontal.setter
    def is_horizontal(self, value: bool):
        if self._is_horizontal != value:
            self._is_horizontal = value
            self.clear_all_caches()
            self.stateChanged.emit()

    @property
    def split_position(self) -> float:
        return self._split_position

    @split_position.setter
    def split_position(self, value: float):
        if self._split_position != value:
            self._split_position = value
            self.stateChanged.emit()

    @property
    def split_position_visual(self) -> float:
        return self._split_position_visual

    @split_position_visual.setter
    def split_position_visual(self, value: float):
        self._split_position_visual = value

    @property
    def use_magnifier(self) -> bool:
        return self._use_magnifier

    @use_magnifier.setter
    def use_magnifier(self, value: bool):
        if self._use_magnifier != value:
            self._use_magnifier = value
            self.clear_all_caches()
            self.stateChanged.emit()

    @property
    def magnifier_size_relative(self) -> float:
        return self._magnifier_size_relative

    @magnifier_size_relative.setter
    def magnifier_size_relative(self, value: float):
        if self._magnifier_size_relative != value:
            self._magnifier_size_relative = value
            self.stateChanged.emit()

    @property
    def capture_size_relative(self) -> float:
        return self._capture_size_relative

    @capture_size_relative.setter
    def capture_size_relative(self, value: float):
        if self._capture_size_relative != value:
            self._capture_size_relative = value
            self.stateChanged.emit()

    @property
    def capture_position_relative(self) -> QPointF:
        return self._capture_position_relative

    @capture_position_relative.setter
    def capture_position_relative(self, value: QPointF):
        if self._capture_position_relative != value:
            self._capture_position_relative = value
            self.stateChanged.emit()

    @property
    def show_capture_area_on_main_image(self) -> bool:
        return self._show_capture_area_on_main_image

    @show_capture_area_on_main_image.setter
    def show_capture_area_on_main_image(self, value: bool):
        if self._show_capture_area_on_main_image != value:
            self._show_capture_area_on_main_image = value
            self.stateChanged.emit()

    @property
    def freeze_magnifier(self) -> bool:
        return self._freeze_magnifier

    @freeze_magnifier.setter
    def freeze_magnifier(self, value: bool):
        if self._freeze_magnifier != value:
            self._freeze_magnifier = value
            self.clear_all_caches()
            self.stateChanged.emit()

    @property
    def frozen_magnifier_absolute_pos(self) -> QPoint | None:
        return self._frozen_magnifier_absolute_pos

    @frozen_magnifier_absolute_pos.setter
    def frozen_magnifier_absolute_pos(self, value: QPoint | None):
        if self._frozen_magnifier_absolute_pos != value:
            self._frozen_magnifier_absolute_pos = value

    @property
    def magnifier_offset_relative(self) -> QPointF:
        return self._magnifier_offset_relative

    @magnifier_offset_relative.setter
    def magnifier_offset_relative(self, value: QPointF):
        if self._magnifier_offset_relative != value:
            self._magnifier_offset_relative = value
            self.stateChanged.emit()

    @property
    def magnifier_spacing_relative(self) -> float:
        return self._magnifier_spacing_relative

    @magnifier_spacing_relative.setter
    def magnifier_spacing_relative(self, value: float):
        if self._magnifier_spacing_relative != value:
            self._magnifier_spacing_relative = value
            self.stateChanged.emit()

    @property
    def magnifier_offset_relative_visual(self) -> QPointF:
        return self._magnifier_offset_relative_visual

    @magnifier_offset_relative_visual.setter
    def magnifier_offset_relative_visual(self, value: QPointF):
        self._magnifier_offset_relative_visual = value

    @property
    def magnifier_spacing_relative_visual(self) -> float:
        return self._magnifier_spacing_relative_visual

    @magnifier_spacing_relative_visual.setter
    def magnifier_spacing_relative_visual(self, value: float):
        self._magnifier_spacing_relative_visual = value

    @property
    def image_display_rect_on_label(self) -> QRect:
        return self._image_display_rect_on_label

    @image_display_rect_on_label.setter
    def image_display_rect_on_label(self, value: QRect):
        self._image_display_rect_on_label = value

    @property
    def movement_speed_per_sec(self) -> float:
        return self._movement_speed_per_sec

    @movement_speed_per_sec.setter
    def movement_speed_per_sec(self, value: float):
        self._movement_speed_per_sec = value

    @property
    def interpolation_method(self) -> str:
        return self._interpolation_method

    @interpolation_method.setter
    def interpolation_method(self, value: str):
        if self._interpolation_method != value:
            self._interpolation_method = value
            self.clear_all_caches()
            self.stateChanged.emit()

    @property
    def max_name_length(self) -> int:
        return self._max_name_length

    @max_name_length.setter
    def max_name_length(self, value: int):
        if self._max_name_length != value:
            self._max_name_length = value
            self.stateChanged.emit()

    @property
    def file_name_color(self) -> QColor:
        return self._file_name_color

    @file_name_color.setter
    def file_name_color(self, value: QColor):
        if self._file_name_color != value:
            self._file_name_color = value
            self.stateChanged.emit()

    @property
    def include_file_names_in_saved(self) -> bool:
        return self._include_file_names_in_saved

    @include_file_names_in_saved.setter
    def include_file_names_in_saved(self, value: bool):
        if self._include_file_names_in_saved != value:
            self._include_file_names_in_saved = value
            self.stateChanged.emit()

    @property
    def font_size_percent(self) -> int:
        return self._font_size_percent

    @font_size_percent.setter
    def font_size_percent(self, value: int):
        if self._font_size_percent != value:
            self._font_size_percent = value
            self.stateChanged.emit()

    @property
    def pixmap_width(self) -> int:
        return self._pixmap_width

    @pixmap_width.setter
    def pixmap_width(self, value: int):
        self._pixmap_width = value

    @property
    def pixmap_height(self) -> int:
        return self._pixmap_height

    @pixmap_height.setter
    def pixmap_height(self, value: int):
        self._pixmap_height = value

    @property
    def is_dragging_split_line(self) -> bool:
        return self._is_dragging_split_line

    @is_dragging_split_line.setter
    def is_dragging_split_line(self, value: bool):
        self._is_dragging_split_line = value

    @property
    def is_dragging_capture_point(self) -> bool:
        return self._is_dragging_capture_point

    @is_dragging_capture_point.setter
    def is_dragging_capture_point(self, value: bool):
        self._is_dragging_capture_point = value

    @property
    def is_dragging_any_slider(self) -> bool:
        return self._is_dragging_any_slider

    @is_dragging_any_slider.setter
    def is_dragging_any_slider(self, value: bool):
        self._is_dragging_any_slider = value

    @property
    def magnifier_is_actively_lerping(self) -> bool:
        return self._magnifier_is_actively_lerping

    @magnifier_is_actively_lerping.setter
    def magnifier_is_actively_lerping(self, value: bool):
        self._magnifier_is_actively_lerping = value

    @property
    def split_is_actively_lerping(self) -> bool:
        return self._split_is_actively_lerping

    @split_is_actively_lerping.setter
    def split_is_actively_lerping(self, value: bool):
        self._split_is_actively_lerping = value

    @property
    def magnifier_is_keyboard_panning(self) -> bool:
        return self._magnifier_is_keyboard_panning

    @magnifier_is_keyboard_panning.setter
    def magnifier_is_keyboard_panning(self, value: bool):
        self._magnifier_is_keyboard_panning = value

    @property
    def is_interactive_mode(self) -> bool:
        return self._is_interactive_mode

    @is_interactive_mode.setter
    def is_interactive_mode(self, value: bool):
        self._is_interactive_mode = value

    @property
    def resize_in_progress(self) -> bool:
        return self._resize_in_progress

    @resize_in_progress.setter
    def resize_in_progress(self, value: bool):
        self._resize_in_progress = value

    @property
    def pressed_keys(self) -> set[int]:
        return self._pressed_keys

    @property
    def space_bar_pressed(self) -> bool:
        return self._space_bar_pressed

    @space_bar_pressed.setter
    def space_bar_pressed(self, value: bool):
        self._space_bar_pressed = value

    @property
    def showing_single_image_mode(self) -> int:
        return self._showing_single_image_mode

    @showing_single_image_mode.setter
    def showing_single_image_mode(self, value: int):
        if self._showing_single_image_mode != value:
            self._showing_single_image_mode = value
            self.stateChanged.emit()

    @property
    def image1_path(self) -> str | None:
        return self._image1_path

    @image1_path.setter
    def image1_path(self, value: str | None):
        self._image1_path = value

    @property
    def image2_path(self) -> str | None:
        return self._image2_path

    @image2_path.setter
    def image2_path(self, value: str | None):
        self._image2_path = value
    
    @property
    def jpeg_quality(self) -> int:
        return self._jpeg_quality

    @jpeg_quality.setter
    def jpeg_quality(self, value: int):
        self._jpeg_quality = value

    def set_current_image_data(self, image_number: int, image_pil: Image.Image |
                            None, image_path: str | None, display_name: str | None):
        def _get_default_display_name(path: str | None) -> str:
            if path:
                base_name = os.path.basename(path)
                return os.path.splitext(base_name)[0]
            return ''

        if image_number == 1:
            self._original_image1 = image_pil
            self._image1_path = image_path
            if 0 <= self._current_index1 < len(self._image_list1):
                img_ref, pth_ref, _ = self._image_list1[self._current_index1]
                final_display_name = display_name if display_name is not None else _get_default_display_name(image_path)
                self._image_list1[self._current_index1] = (img_ref if img_ref is not None else image_pil, pth_ref if pth_ref is not None else image_path, final_display_name)
        elif image_number == 2:
            self._original_image2 = image_pil
            self._image2_path = image_path
            if 0 <= self._current_index2 < len(self._image_list2):
                img_ref, pth_ref, _ = self._image_list2[self._current_index2]
                final_display_name = display_name if display_name is not None else _get_default_display_name(image_path)
                self._image_list2[self._current_index2] = (img_ref if img_ref is not None else image_pil, pth_ref if pth_ref is not None else image_path, final_display_name)

        self._image1 = None
        self._image2 = None
        
        self.clear_all_caches()
        self._split_position_visual = self._split_position
        self.stateChanged.emit()

    def swap_all_image_data(self):
        self._original_image1, self._original_image2 = (
            self._original_image2, self._original_image1)
        self._image1_path, self._image2_path = (
            self._image2_path, self._image1_path)
        self._image_list1, self._image_list2 = (
            self._image_list2, self._image_list1)
        self._current_index1, self._current_index2 = (
            self._current_index2, self._current_index1)
        self._image1 = None
        self._image2 = None
        self.clear_all_caches()
        self._split_position_visual = self._split_position
        self.stateChanged.emit()

    def clear_image_slot_data(self, image_number: int):
        if image_number == 1:
            self._image_list1.clear()
            self._current_index1 = -1
            self._original_image1 = None
            self._image1_path = None
            self._image1 = None
        elif image_number == 2:
            self._image_list2.clear()
            self._current_index2 = -1
            self._original_image2 = None
            self._image2_path = None
            self._image2 = None
        if image_number == 1 and self._original_image2:
            self._image2 = None
        if image_number == 2 and self._original_image1:
            self._image1 = None
        self.clear_all_caches()
        self._split_position_visual = self._split_position
        self.stateChanged.emit()
    
    def get_current_display_name(
            self, image_number: int) -> str:
        if image_number == 1 and 0 <= self._current_index1 < len(
                self._image_list1):
            return self._image_list1[self._current_index1][2]
        if image_number == 2 and 0 <= self._current_index2 < len(
                self._image_list2):
            return self._image_list2[self._current_index2][2]
        return ''

    def get_image_dimensions(
            self, image_number: int) -> tuple[int, int] | None:
        img = self._original_image1 if image_number == 1 else self._original_image2
        if img and hasattr(img, 'size'):
            return img.size
        return None