import logging

from PIL import Image
from PyQt6.QtCore import QByteArray, QObject, QPoint, QPointF, QRect, pyqtSignal
from PyQt6.QtGui import QColor

from .constants import AppConstants

logger = logging.getLogger("ImproveImgSLI")

class AppState(QObject):
    stateChanged = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._image_list1: list[tuple[Image.Image | None, str, str, int]] = []
        self._image_list2: list[tuple[Image.Image | None, str, str, int]] = []
        self._current_index1: int = -1
        self._current_index2: int = -1

        self._original_image1: Image.Image | None = None
        self._original_image2: Image.Image | None = None
        self._preview_image1: Image.Image | None = None
        self._preview_image2: Image.Image | None = None

        self._full_res_image1: Image.Image | None = None
        self._full_res_image2: Image.Image | None = None
        self._image1_path: str | None = None
        self._image2_path: str | None = None
        self.fixed_label_width: int | None = None
        self.fixed_label_height: int | None = None

        self._image1: Image.Image | None = None
        self._image2: Image.Image | None = None
        self._display_cache_image1: Image.Image | None = None
        self._display_cache_image2: Image.Image | None = None
        self._scaled_image1_for_display: Image.Image | None = None
        self._scaled_image2_for_display: Image.Image | None = None
        self._cached_scaled_image_dims: tuple[int, int] | None = None
        self._last_display_cache_params: tuple | None = None
        self._cached_split_base_image: Image.Image | None = None
        self._last_split_cached_params: tuple | None = None
        self._magnifier_cache: dict = {}

        self._unified_image_cache: dict = {}
        self._unified_image_cache_keys: list = []

        self._split_position: float = 0.5
        self._split_position_visual: float = 0.5
        self._is_horizontal: bool = False
        self._diff_mode: str = 'off'
        self._channel_view_mode: str = 'RGB'
        self._auto_calculate_psnr: bool = False
        self._auto_calculate_ssim: bool = False

        self._psnr_value: float | None = None
        self._ssim_value: float | None = None

        self._use_magnifier: bool = False
        self._magnifier_size_relative: float = (
            AppConstants.DEFAULT_MAGNIFIER_SIZE_RELATIVE
        )
        self._capture_size_relative: float = AppConstants.DEFAULT_CAPTURE_SIZE_RELATIVE
        self._capture_position_relative: QPointF = (
            AppConstants.DEFAULT_CAPTURE_POS_RELATIVE
        )
        self._show_capture_area_on_main_image: bool = True
        self._freeze_magnifier: bool = False
        self._frozen_capture_point_relative: QPointF | None = None
        self._magnifier_offset_relative: QPointF = (
            AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        )
        self._magnifier_spacing_relative: float = (
            AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        )
        self._magnifier_offset_relative_visual: QPointF = QPointF(
            AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        )
        self._magnifier_spacing_relative_visual: float = (
            AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        )
        self._magnifier_is_horizontal: bool = False

        self._magnifier_visible_left: bool = True
        self._magnifier_visible_center: bool = True
        self._magnifier_visible_right: bool = True

        try:
            default_spacing = AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
            half_spacing = default_spacing / 2.0
        except Exception:
            half_spacing = 0.05
        self._magnifier_left_offset_relative: QPointF = QPointF(-half_spacing, 0.0)
        self._magnifier_right_offset_relative: QPointF = QPointF(half_spacing, 0.0)
        self._magnifier_left_offset_relative_visual: QPointF = QPointF(-half_spacing, 0.0)
        self._magnifier_right_offset_relative_visual: QPointF = QPointF(half_spacing, 0.0)

        self._display_resolution_limit: int = (
            AppConstants.DEFAULT_DISPLAY_RESOLUTION_LIMIT
        )
        self._interpolation_method: str = AppConstants.DEFAULT_INTERPOLATION_METHOD
        self._optimize_magnifier_movement: bool = True
        self._movement_interpolation_method: str = "BILINEAR"
        self._include_file_names_in_saved: bool = False
        self._font_size_percent: int = 100
        self._font_weight: int = 0
        self._text_alpha_percent: int = 100
        self._movement_speed_per_sec: float = 2.0
        self._max_name_length: int = 30
        self._file_name_color: QColor = QColor(255, 0, 0, 255)
        self._file_name_bg_color: QColor = QColor(0, 0, 0, 80)
        self._draw_text_background: bool = True
        self._text_placement_mode: str = "edges"
        self._jpeg_quality: int = AppConstants.DEFAULT_JPEG_QUALITY
        self._current_language: str = "en"
        self.debug_mode_enabled: bool = True
        self.system_notifications_enabled: bool = True
        self._theme: str = "auto"
        self._ui_font_mode: str = "builtin"
        self._ui_font_family: str = ""

        self._pixmap_width: int = 0
        self._pixmap_height: int = 0
        self._image_display_rect_on_label = QRect()
        self._is_dragging_split_line: bool = False
        self._is_dragging_capture_point: bool = False
        self._is_dragging_split_in_magnifier: bool = False
        self._is_dragging_any_slider: bool = False

        self._magnifier_screen_center: QPoint = QPoint()
        self._magnifier_screen_size: int = 0
        self._is_magnifier_combined: bool = False

        self._magnifier_internal_split: float = 0.5
        self._is_interactive_mode: bool = False
        self._resize_in_progress: bool = False
        self._text_bg_visual_height: float = 0.0
        self._text_bg_visual_width: float = 0.0
        self._pressed_keys: set[int] = set()
        self._space_bar_pressed: bool = False
        self._showing_single_image_mode: int = 0
        self._fixed_label_width: int | None = None
        self._fixed_label_height: int | None = None
        self.loaded_geometry: QByteArray = QByteArray()
        self.loaded_was_maximized: bool = False
        self.loaded_previous_geometry: QByteArray = QByteArray()
        self.loaded_theme: str = "auto"
        self.loaded_image1_paths: list[str] = []
        self.loaded_image2_paths: list[str] = []
        self.loaded_current_index1: int = -1
        self.loaded_current_index2: int = -1
        self.loaded_debug_mode_enabled: bool = False

        self._export_use_default_dir: bool = True
        self._export_default_dir: str | None = None
        self._export_favorite_dir: str | None = None
        self._export_last_format: str = "PNG"
        self._export_quality: int = AppConstants.DEFAULT_JPEG_QUALITY
        self._export_fill_background: bool = False
        self._export_background_color: QColor = QColor(255, 255, 255, 255)
        self._export_last_filename: str = ""
        self._export_png_compress_level: int = 9

        self._divider_line_visible: bool = True
        self._divider_line_color: QColor = QColor(255, 255, 255, 255)
        self._divider_line_thickness: int = 3

        self._magnifier_divider_visible: bool = True
        self._magnifier_divider_color: QColor = QColor(255, 255, 255, 230)
        self._magnifier_divider_thickness: int = 2

    def clear_all_caches(self):
        self._scaled_image1_for_display = None
        self._scaled_image2_for_display = None
        self._cached_scaled_image_dims = None
        self._display_cache_image1 = None
        self._display_cache_image2 = None
        self._last_display_cache_params = None

        self._unified_image_cache.clear()
        self._unified_image_cache_keys.clear()

        self.clear_interactive_caches()

    def clear_interactive_caches(self):
        self._cached_split_base_image = None
        self._last_split_cached_params = None
        self._magnifier_cache.clear()
        self._text_bg_visual_height = 0.0
        self._text_bg_visual_width = 0.0

    def copy_for_worker(self):
        new_state = AppState()
        new_state.split_position_visual = self.split_position_visual
        new_state.is_horizontal = self.is_horizontal
        new_state.diff_mode = self.diff_mode
        new_state.channel_view_mode = self.channel_view_mode
        new_state.use_magnifier = self.use_magnifier
        new_state.show_capture_area_on_main_image = self.show_capture_area_on_main_image
        new_state.capture_position_relative = QPointF(self.capture_position_relative)
        new_state.magnifier_offset_relative_visual = QPointF(
            self.magnifier_offset_relative_visual
        )
        new_state.magnifier_spacing_relative_visual = (
            self.magnifier_spacing_relative_visual
        )
        new_state.magnifier_size_relative = self.magnifier_size_relative
        new_state.capture_size_relative = self.capture_size_relative
        new_state.freeze_magnifier = self.freeze_magnifier
        if self.frozen_capture_point_relative:
            new_state.frozen_capture_point_relative = QPointF(self.frozen_capture_point_relative)
        new_state.include_file_names_in_saved = self.include_file_names_in_saved
        new_state.font_size_percent = self.font_size_percent
        new_state.font_weight = self.font_weight
        new_state.text_alpha_percent = self.text_alpha_percent
        new_state.max_name_length = self.max_name_length
        new_state.file_name_color = QColor(self.file_name_color)
        new_state.file_name_bg_color = QColor(self.file_name_bg_color)
        new_state.draw_text_background = self.draw_text_background
        new_state.text_placement_mode = self.text_placement_mode
        new_state.interpolation_method = self.interpolation_method
        new_state.is_interactive_mode = self.is_interactive_mode
        new_state.text_bg_visual_height = self.text_bg_visual_height
        new_state.text_bg_visual_width = self.text_bg_visual_width
        new_state.text_placement_mode = self.text_placement_mode
        new_state.divider_line_visible = self.divider_line_visible
        new_state.divider_line_color = QColor(self.divider_line_color)
        new_state.divider_line_thickness = self.divider_line_thickness
        new_state.magnifier_screen_center = QPoint(self.magnifier_screen_center)
        new_state.magnifier_screen_size = self.magnifier_screen_size
        new_state.is_magnifier_combined = self.is_magnifier_combined
        new_state.magnifier_internal_split = self.magnifier_internal_split
        new_state.magnifier_is_horizontal = self.magnifier_is_horizontal
        new_state.magnifier_divider_visible = self.magnifier_divider_visible
        new_state.magnifier_divider_color = QColor(self.magnifier_divider_color)
        new_state.magnifier_divider_thickness = self.magnifier_divider_thickness
        new_state.optimize_magnifier_movement = self.optimize_magnifier_movement
        new_state.movement_interpolation_method = self.movement_interpolation_method

        try:
            new_state.magnifier_visible_left = self.magnifier_visible_left
            new_state.magnifier_visible_center = self.magnifier_visible_center
            new_state.magnifier_visible_right = self.magnifier_visible_right
        except Exception:
            pass

        try:
            new_state.magnifier_left_offset_relative = QPointF(self.magnifier_left_offset_relative)
            new_state.magnifier_right_offset_relative = QPointF(self.magnifier_right_offset_relative)
            new_state.magnifier_left_offset_relative_visual = QPointF(self.magnifier_left_offset_relative_visual)
            new_state.magnifier_right_offset_relative_visual = QPointF(self.magnifier_right_offset_relative_visual)
        except Exception:
            pass

        return new_state

    @property
    def text_alpha_percent(self) -> int:
        return getattr(self, "_text_alpha_percent", 100)

    @text_alpha_percent.setter
    def text_alpha_percent(self, value: int):
        try:
            clamped = max(0, min(100, int(value)))
        except Exception:
            clamped = 100
        self._text_alpha_percent = clamped

    @property
    def image_list1(self) -> list[tuple[Image.Image | None, str, str, int]]:
        return self._image_list1

    @property
    def image_list2(self) -> list[tuple[Image.Image | None, str, str, int]]:
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
        return self._preview_image1

    @original_image1.setter
    def original_image1(self, value: Image.Image | None):
        self._preview_image1 = value

    @property
    def original_image2(self) -> Image.Image | None:
        return self._preview_image2

    @original_image2.setter
    def original_image2(self, value: Image.Image | None):
        self._preview_image2 = value

    @property
    def preview_image1(self) -> Image.Image | None:
        return self._preview_image1

    @property
    def preview_image2(self) -> Image.Image | None:
        return self._preview_image2

    @property
    def full_res_image1(self) -> Image.Image | None:
        return self._full_res_image1

    @full_res_image1.setter
    def full_res_image1(self, value: Image.Image | None):
        self._full_res_image1 = value

    @property
    def full_res_image2(self) -> Image.Image | None:
        return self._full_res_image2

    @full_res_image2.setter
    def full_res_image2(self, value: Image.Image | None):
        self._full_res_image2 = value

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
    def is_horizontal(self) -> bool:
        return self._is_horizontal

    @is_horizontal.setter
    def is_horizontal(self, value: bool):
        if self._is_horizontal != value:
            self._is_horizontal = value
            self.clear_interactive_caches()
            self.stateChanged.emit()

    @property
    def diff_mode(self) -> str:
        return self._diff_mode

    @diff_mode.setter
    def diff_mode(self, value: str):
        self._diff_mode = value

    @property
    def channel_view_mode(self) -> str:
        return self._channel_view_mode

    @channel_view_mode.setter
    def channel_view_mode(self, value: str):
        self._channel_view_mode = value

    @property
    def psnr_value(self) -> float | None:
        return self._psnr_value

    @psnr_value.setter
    def psnr_value(self, value: float | None):
        self._psnr_value = value

    @property
    def ssim_value(self) -> float | None:
        return self._ssim_value

    @ssim_value.setter
    def ssim_value(self, value: float | None):
        self._ssim_value = value

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
            self.stateChanged.emit()

    @property
    def freeze_magnifier(self) -> bool:
        return self._freeze_magnifier

    @freeze_magnifier.setter
    def freeze_magnifier(self, value: bool):
        if self._freeze_magnifier != value:
            self._freeze_magnifier = value
            self.clear_interactive_caches()
            self.stateChanged.emit()

    @property
    def interpolation_method(self) -> str:
        return self._interpolation_method

    @interpolation_method.setter
    def interpolation_method(self, value: str):
        if self._interpolation_method != value:
            self._interpolation_method = value
            self.clear_interactive_caches()
            self.stateChanged.emit()

    @property
    def display_resolution_limit(self) -> int:
        return self._display_resolution_limit

    @display_resolution_limit.setter
    def display_resolution_limit(self, value: int):
        if self._display_resolution_limit != value:
            self._display_resolution_limit = value
            self.clear_all_caches()
            self.stateChanged.emit()

    def _create_simple_property(name, signal_on_change=True):
        private_name = f"_{name}"

        def getter(self):
            return getattr(self, private_name)

        def setter(self, value):
            if getattr(self, private_name) != value:
                setattr(self, private_name, value)
                if signal_on_change:
                    self.stateChanged.emit()

        return property(getter, setter)

    theme = _create_simple_property("theme")
    ui_font_mode = _create_simple_property("ui_font_mode")
    ui_font_family = _create_simple_property("ui_font_family")

    magnifier_size_relative = _create_simple_property("magnifier_size_relative")
    capture_size_relative = _create_simple_property("capture_size_relative")
    capture_position_relative = _create_simple_property("capture_position_relative")
    show_capture_area_on_main_image = _create_simple_property(
        "show_capture_area_on_main_image"
    )
    frozen_capture_point_relative = _create_simple_property(
        "frozen_capture_point_relative", False
    )
    magnifier_offset_relative = _create_simple_property("magnifier_offset_relative")
    magnifier_spacing_relative = _create_simple_property("magnifier_spacing_relative")
    magnifier_offset_relative_visual = _create_simple_property(
        "magnifier_offset_relative_visual", False
    )
    magnifier_spacing_relative_visual = _create_simple_property(
        "magnifier_spacing_relative_visual", False
    )

    magnifier_left_offset_relative = _create_simple_property("magnifier_left_offset_relative")
    magnifier_right_offset_relative = _create_simple_property("magnifier_right_offset_relative")
    magnifier_left_offset_relative_visual = _create_simple_property(
        "magnifier_left_offset_relative_visual", False
    )
    magnifier_right_offset_relative_visual = _create_simple_property(
        "magnifier_right_offset_relative_visual", False
    )
    include_file_names_in_saved = _create_simple_property("include_file_names_in_saved")
    magnifier_is_horizontal = _create_simple_property("magnifier_is_horizontal")
    font_size_percent = _create_simple_property("font_size_percent")
    font_weight = _create_simple_property("font_weight")
    max_name_length = _create_simple_property("max_name_length")
    file_name_color = _create_simple_property("file_name_color")
    file_name_bg_color = _create_simple_property("file_name_bg_color")
    draw_text_background = _create_simple_property("draw_text_background")
    text_placement_mode = _create_simple_property("text_placement_mode")
    current_language = _create_simple_property("current_language")
    showing_single_image_mode = _create_simple_property("showing_single_image_mode")

    image_display_rect_on_label = _create_simple_property(
        "image_display_rect_on_label", False
    )
    pixmap_width = _create_simple_property("pixmap_width", False)
    pixmap_height = _create_simple_property("pixmap_height", False)
    is_dragging_split_line = _create_simple_property("is_dragging_split_line", False)
    is_dragging_capture_point = _create_simple_property(
        "is_dragging_capture_point", False
    )
    is_dragging_split_in_magnifier = _create_simple_property(
        "is_dragging_split_in_magnifier", False
    )
    is_dragging_any_slider = _create_simple_property("is_dragging_any_slider", False)

    magnifier_screen_center = _create_simple_property("magnifier_screen_center", False)
    magnifier_screen_size = _create_simple_property("magnifier_screen_size", False)
    is_magnifier_combined = _create_simple_property("is_magnifier_combined", False)
    magnifier_internal_split = _create_simple_property("magnifier_internal_split")
    is_interactive_mode = _create_simple_property("is_interactive_mode", False)
    resize_in_progress = _create_simple_property("resize_in_progress", False)
    text_bg_visual_height = _create_simple_property("text_bg_visual_height", False)
    text_bg_visual_width = _create_simple_property("text_bg_visual_width", False)
    space_bar_pressed = _create_simple_property("space_bar_pressed", False)
    image1_path = _create_simple_property("image1_path", False)
    image2_path = _create_simple_property("image2_path", False)
    jpeg_quality = _create_simple_property("jpeg_quality", False)
    movement_speed_per_sec = _create_simple_property("movement_speed_per_sec", False)

    scaled_image1_for_display = _create_simple_property(
        "scaled_image1_for_display", False
    )
    scaled_image2_for_display = _create_simple_property(
        "scaled_image2_for_display", False
    )

    export_use_default_dir = _create_simple_property("export_use_default_dir")
    export_default_dir = _create_simple_property("export_default_dir")
    export_favorite_dir = _create_simple_property("export_favorite_dir")
    export_last_format = _create_simple_property("export_last_format")
    export_quality = _create_simple_property("export_quality")
    export_fill_background = _create_simple_property("export_fill_background")
    export_background_color = _create_simple_property("export_background_color")
    export_last_filename = _create_simple_property("export_last_filename")
    export_png_compress_level = _create_simple_property("export_png_compress_level")

    divider_line_visible = _create_simple_property("divider_line_visible")
    divider_line_color = _create_simple_property("divider_line_color")
    divider_line_thickness = _create_simple_property("divider_line_thickness")

    magnifier_divider_visible = _create_simple_property("magnifier_divider_visible")
    magnifier_divider_color = _create_simple_property("magnifier_divider_color")
    magnifier_divider_thickness = _create_simple_property("magnifier_divider_thickness")

    magnifier_visible_left = _create_simple_property("magnifier_visible_left")
    magnifier_visible_center = _create_simple_property("magnifier_visible_center")
    magnifier_visible_right = _create_simple_property("magnifier_visible_right")

    optimize_magnifier_movement = _create_simple_property("optimize_magnifier_movement")
    movement_interpolation_method = _create_simple_property("movement_interpolation_method")
    auto_calculate_psnr = _create_simple_property("auto_calculate_psnr")
    auto_calculate_ssim = _create_simple_property("auto_calculate_ssim")

    @property
    def pressed_keys(self) -> set[int]:
        return self._pressed_keys

    def set_current_image_data(
            self,
            image_number: int,
            image_pil: Image.Image | None,
            image_path: str | None,
            display_name: str | None,
        ):
            target_list = self._image_list1 if image_number == 1 else self._image_list2
            current_index = self._current_index1 if image_number == 1 else self._current_index2

            if image_number == 1:
                if self._image1_path != image_path:
                    self._image1 = None
                self._preview_image1 = image_pil
                self._full_res_image1 = image_pil
                self._image1_path = image_path
            else:
                if self._image2_path != image_path:
                    self._image2 = None
                self._preview_image2 = image_pil
                self._full_res_image2 = image_pil
                self._image2_path = image_path

            if 0 <= current_index < len(target_list):
                img_ref, pth_ref, _, score = target_list[current_index]
                final_display_name = (
                    display_name if display_name is not None else target_list[current_index][2]
                )
                target_list[current_index] = (
                    img_ref or image_pil,
                    pth_ref or image_path,
                    final_display_name,
                    score,
                )

            self._split_position_visual = self._split_position

    def set_full_res_image(self, image_number: int, full_image_pil: Image.Image | None):
        if image_number == 1:
            if self._full_res_image1 is not full_image_pil:
                self._full_res_image1 = full_image_pil
                self.clear_all_caches()
                self.stateChanged.emit()
        else:
            if self._full_res_image2 is not full_image_pil:
                self._full_res_image2 = full_image_pil
                self.clear_all_caches()
                self.stateChanged.emit()

    def swap_all_image_data(self):
        self._image_list1, self._image_list2 = self._image_list2, self._image_list1
        self._current_index1, self._current_index2 = (
            self._current_index2,
            self._current_index1,
        )
        self._preview_image1, self._preview_image2 = (
            self._preview_image2,
            self._preview_image1,
        )
        self._full_res_image1, self._full_res_image2 = (
            self._full_res_image2,
            self._full_res_image1,
        )
        self._image1_path, self._image2_path = self._image2_path, self._image1_path

        self._image1 = None
        self._image2 = None
        self.clear_all_caches()
        self._split_position_visual = self._split_position
        self.stateChanged.emit()

    def clear_image_slot_data(self, image_number: int):
        if image_number == 1:
            self._image_list1.clear()
            self._current_index1 = -1
            self._preview_image1 = None
            self._full_res_image1 = None
            self._image1_path = None
        else:
            self._image_list2.clear()
            self._current_index2 = -1
            self._preview_image2 = None
            self._full_res_image2 = None
            self._image2_path = None

        self._image1 = None
        self._image2 = None
        self.clear_all_caches()
        self._split_position_visual = self._split_position

    def get_current_display_name(self, image_number: int) -> str:
        target_list, index = (
            (self._image_list1, self._current_index1)
            if image_number == 1
            else (self._image_list2, self._current_index2)
        )
        if 0 <= index < len(target_list):
            return target_list[index][2]
        return ""

    def get_current_score(self, image_number: int) -> int | None:
        target_list, index = (
            (self._image_list1, self._current_index1)
            if image_number == 1
            else (self._image_list2, self._current_index2)
        )
        if 0 <= index < len(target_list):
            return target_list[index][3]
        return None

    def get_image_dimensions(self, image_number: int) -> tuple[int, int] | None:

        img = None
        if image_number == 1:
            img = self._full_res_image1 or self._preview_image1
        else:
            img = self._full_res_image2 or self._preview_image2
        if img and hasattr(img, "size"):
            return img.size
        return None
