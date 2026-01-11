

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from PyQt6.QtCore import QPointF, QPoint, QRect
from PyQt6.QtGui import QColor

class ActionType(Enum):

    SET_SPLIT_POSITION = "SET_SPLIT_POSITION"
    SET_SPLIT_POSITION_VISUAL = "SET_SPLIT_POSITION_VISUAL"
    TOGGLE_ORIENTATION = "TOGGLE_ORIENTATION"
    SET_MAGNIFIER_SIZE_RELATIVE = "SET_MAGNIFIER_SIZE_RELATIVE"
    SET_CAPTURE_SIZE_RELATIVE = "SET_CAPTURE_SIZE_RELATIVE"
    TOGGLE_MAGNIFIER = "TOGGLE_MAGNIFIER"
    SET_MAGNIFIER_VISIBILITY = "SET_MAGNIFIER_VISIBILITY"
    TOGGLE_MAGNIFIER_ORIENTATION = "TOGGLE_MAGNIFIER_ORIENTATION"
    TOGGLE_FREEZE_MAGNIFIER = "TOGGLE_FREEZE_MAGNIFIER"
    SET_MAGNIFIER_POSITION = "SET_MAGNIFIER_POSITION"
    SET_MAGNIFIER_INTERNAL_SPLIT = "SET_MAGNIFIER_INTERNAL_SPLIT"
    SET_MOVEMENT_SPEED = "SET_MOVEMENT_SPEED"
    UPDATE_MAGNIFIER_COMBINED_STATE = "UPDATE_MAGNIFIER_COMBINED_STATE"
    SET_IS_DRAGGING_SLIDER = "SET_IS_DRAGGING_SLIDER"
    SET_INTERACTIVE_MODE = "SET_INTERACTIVE_MODE"
    SET_IS_DRAGGING_SPLIT_LINE = "SET_IS_DRAGGING_SPLIT_LINE"
    SET_IS_DRAGGING_CAPTURE_POINT = "SET_IS_DRAGGING_CAPTURE_POINT"
    SET_IS_DRAGGING_SPLIT_IN_MAGNIFIER = "SET_IS_DRAGGING_SPLIT_IN_MAGNIFIER"
    SET_PIXMAP_DIMENSIONS = "SET_PIXMAP_DIMENSIONS"
    SET_IMAGE_DISPLAY_RECT = "SET_IMAGE_DISPLAY_RECT"
    SET_FIXED_LABEL_DIMENSIONS = "SET_FIXED_LABEL_DIMENSIONS"
    SET_RESIZE_IN_PROGRESS = "SET_RESIZE_IN_PROGRESS"
    SET_SHOWING_SINGLE_IMAGE_MODE = "SET_SHOWING_SINGLE_IMAGE_MODE"
    SET_PRESSED_KEYS = "SET_PRESSED_KEYS"
    SET_SPACE_BAR_PRESSED = "SET_SPACE_BAR_PRESSED"
    SET_MAGNIFIER_OFFSET_RELATIVE = "SET_MAGNIFIER_OFFSET_RELATIVE"
    SET_MAGNIFIER_SPACING_RELATIVE = "SET_MAGNIFIER_SPACING_RELATIVE"
    SET_MAGNIFIER_OFFSET_RELATIVE_VISUAL = "SET_MAGNIFIER_OFFSET_RELATIVE_VISUAL"
    SET_MAGNIFIER_SPACING_RELATIVE_VISUAL = "SET_MAGNIFIER_SPACING_RELATIVE_VISUAL"
    SET_ACTIVE_MAGNIFIER_ID = "SET_ACTIVE_MAGNIFIER_ID"
    SET_MAGNIFIER_SCREEN_CENTER = "SET_MAGNIFIER_SCREEN_CENTER"
    SET_MAGNIFIER_SCREEN_SIZE = "SET_MAGNIFIER_SCREEN_SIZE"
    SET_OPTIMIZE_MAGNIFIER_MOVEMENT = "SET_OPTIMIZE_MAGNIFIER_MOVEMENT"
    SET_HIGHLIGHTED_MAGNIFIER_ELEMENT = "SET_HIGHLIGHTED_MAGNIFIER_ELEMENT"

    SET_DIFF_MODE = "SET_DIFF_MODE"
    SET_CHANNEL_VIEW_MODE = "SET_CHANNEL_VIEW_MODE"
    SET_CACHED_DIFF_IMAGE = "SET_CACHED_DIFF_IMAGE"

    SET_DIVIDER_LINE_VISIBLE = "SET_DIVIDER_LINE_VISIBLE"
    SET_DIVIDER_LINE_COLOR = "SET_DIVIDER_LINE_COLOR"
    SET_DIVIDER_LINE_THICKNESS = "SET_DIVIDER_LINE_THICKNESS"
    SET_MAGNIFIER_DIVIDER_VISIBLE = "SET_MAGNIFIER_DIVIDER_VISIBLE"
    SET_MAGNIFIER_DIVIDER_COLOR = "SET_MAGNIFIER_DIVIDER_COLOR"
    SET_MAGNIFIER_DIVIDER_THICKNESS = "SET_MAGNIFIER_DIVIDER_THICKNESS"
    SET_MAGNIFIER_BORDER_COLOR = "SET_MAGNIFIER_BORDER_COLOR"
    SET_MAGNIFIER_LASER_COLOR = "SET_MAGNIFIER_LASER_COLOR"
    SET_CAPTURE_RING_COLOR = "SET_CAPTURE_RING_COLOR"
    SET_INTERPOLATION_METHOD = "SET_INTERPOLATION_METHOD"
    SET_MOVEMENT_INTERPOLATION_METHOD = "SET_MOVEMENT_INTERPOLATION_METHOD"
    SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD = "SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD"
    SET_LASER_SMOOTHING_INTERPOLATION_METHOD = "SET_LASER_SMOOTHING_INTERPOLATION_METHOD"
    SET_OPTIMIZE_LASER_SMOOTHING = "SET_OPTIMIZE_LASER_SMOOTHING"
    SET_SHOW_MAGNIFIER_GUIDES = "SET_SHOW_MAGNIFIER_GUIDES"
    SET_MAGNIFIER_GUIDES_THICKNESS = "SET_MAGNIFIER_GUIDES_THICKNESS"
    SET_INCLUDE_FILE_NAMES_IN_SAVED = "SET_INCLUDE_FILE_NAMES_IN_SAVED"
    SET_FONT_SIZE_PERCENT = "SET_FONT_SIZE_PERCENT"
    SET_FONT_WEIGHT = "SET_FONT_WEIGHT"
    SET_TEXT_ALPHA_PERCENT = "SET_TEXT_ALPHA_PERCENT"
    SET_FILE_NAME_COLOR = "SET_FILE_NAME_COLOR"
    SET_FILE_NAME_BG_COLOR = "SET_FILE_NAME_BG_COLOR"
    SET_DRAW_TEXT_BACKGROUND = "SET_DRAW_TEXT_BACKGROUND"
    SET_TEXT_PLACEMENT_MODE = "SET_TEXT_PLACEMENT_MODE"
    SET_MAX_NAME_LENGTH = "SET_MAX_NAME_LENGTH"
    SET_SHOW_CAPTURE_AREA_ON_MAIN_IMAGE = "SET_SHOW_CAPTURE_AREA_ON_MAIN_IMAGE"

    SET_CURRENT_INDEX = "SET_CURRENT_INDEX"
    SET_IMAGE_LIST = "SET_IMAGE_LIST"
    SET_ORIGINAL_IMAGE = "SET_ORIGINAL_IMAGE"
    SET_FULL_RES_IMAGE = "SET_FULL_RES_IMAGE"
    SET_PREVIEW_IMAGE = "SET_PREVIEW_IMAGE"
    SET_IMAGE_PATH = "SET_IMAGE_PATH"
    SET_FULL_RES_READY = "SET_FULL_RES_READY"
    SET_PREVIEW_READY = "SET_PREVIEW_READY"
    SET_PROGRESSIVE_LOAD_IN_PROGRESS = "SET_PROGRESSIVE_LOAD_IN_PROGRESS"

    SET_LANGUAGE = "SET_LANGUAGE"
    SET_THEME = "SET_THEME"
    SET_UI_FONT_MODE = "SET_UI_FONT_MODE"
    SET_UI_FONT_FAMILY = "SET_UI_FONT_FAMILY"
    SET_UI_MODE = "SET_UI_MODE"
    SET_DEBUG_MODE_ENABLED = "SET_DEBUG_MODE_ENABLED"
    SET_SYSTEM_NOTIFICATIONS_ENABLED = "SET_SYSTEM_NOTIFICATIONS_ENABLED"
    SET_AUTO_CROP_BLACK_BORDERS = "SET_AUTO_CROP_BLACK_BORDERS"
    SET_VIDEO_RECORDING_FPS = "SET_VIDEO_RECORDING_FPS"
    SET_EXPORT_USE_DEFAULT_DIR = "SET_EXPORT_USE_DEFAULT_DIR"
    SET_EXPORT_DEFAULT_DIR = "SET_EXPORT_DEFAULT_DIR"
    SET_EXPORT_FAVORITE_DIR = "SET_EXPORT_FAVORITE_DIR"
    SET_EXPORT_VIDEO_FAVORITE_DIR = "SET_EXPORT_VIDEO_FAVORITE_DIR"
    SET_EXPORT_LAST_FORMAT = "SET_EXPORT_LAST_FORMAT"
    SET_EXPORT_QUALITY = "SET_EXPORT_QUALITY"
    SET_EXPORT_FILL_BACKGROUND = "SET_EXPORT_FILL_BACKGROUND"
    SET_EXPORT_BACKGROUND_COLOR = "SET_EXPORT_BACKGROUND_COLOR"
    SET_EXPORT_LAST_FILENAME = "SET_EXPORT_LAST_FILENAME"
    SET_EXPORT_PNG_COMPRESS_LEVEL = "SET_EXPORT_PNG_COMPRESS_LEVEL"
    SET_EXPORT_COMMENT_TEXT = "SET_EXPORT_COMMENT_TEXT"
    SET_EXPORT_COMMENT_KEEP_DEFAULT = "SET_EXPORT_COMMENT_KEEP_DEFAULT"
    SET_WINDOW_GEOMETRY = "SET_WINDOW_GEOMETRY"
    SET_WINDOW_WAS_MAXIMIZED = "SET_WINDOW_WAS_MAXIMIZED"

    INVALIDATE_RENDER_CACHE = "INVALIDATE_RENDER_CACHE"
    INVALIDATE_GEOMETRY_CACHE = "INVALIDATE_GEOMETRY_CACHE"
    CLEAR_ALL_CACHES = "CLEAR_ALL_CACHES"
    CLEAR_IMAGE_SLOT_DATA = "CLEAR_IMAGE_SLOT_DATA"

@dataclass
class Action(ABC):
    type: ActionType

    @abstractmethod
    def get_payload(self) -> dict[str, Any]:
        pass

@dataclass
class SetSplitPositionAction(Action):
    position: float

    def __init__(self, position: float):
        super().__init__(type=ActionType.SET_SPLIT_POSITION)
        self.position = position

    def get_payload(self) -> dict[str, Any]:
        return {"position": self.position}

@dataclass
class SetSplitPositionVisualAction(Action):
    position: float

    def __init__(self, position: float):
        super().__init__(type=ActionType.SET_SPLIT_POSITION_VISUAL)
        self.position = position

    def get_payload(self) -> dict[str, Any]:
        return {"position": self.position}

@dataclass
class ToggleOrientationAction(Action):
    is_horizontal: bool

    def __init__(self, is_horizontal: bool):
        super().__init__(type=ActionType.TOGGLE_ORIENTATION)
        self.is_horizontal = is_horizontal

    def get_payload(self) -> dict[str, Any]:
        return {"is_horizontal": self.is_horizontal}

@dataclass
class SetMagnifierSizeRelativeAction(Action):
    size: float

    def __init__(self, size: float):
        super().__init__(type=ActionType.SET_MAGNIFIER_SIZE_RELATIVE)
        self.size = size

    def get_payload(self) -> dict[str, Any]:
        return {"size": self.size}

@dataclass
class SetCaptureSizeRelativeAction(Action):
    size: float

    def __init__(self, size: float):
        super().__init__(type=ActionType.SET_CAPTURE_SIZE_RELATIVE)
        self.size = size

    def get_payload(self) -> dict[str, Any]:
        return {"size": self.size}

@dataclass
class ToggleMagnifierAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.TOGGLE_MAGNIFIER)
        self.enabled = enabled

    def get_payload(self) -> dict[str, Any]:
        return {"enabled": self.enabled}

@dataclass
class SetMagnifierVisibilityAction(Action):
    left: Optional[bool] = None
    center: Optional[bool] = None
    right: Optional[bool] = None

    def __init__(self, left: Optional[bool] = None, center: Optional[bool] = None, right: Optional[bool] = None):
        super().__init__(type=ActionType.SET_MAGNIFIER_VISIBILITY)
        self.left = left
        self.center = center
        self.right = right

    def get_payload(self) -> dict[str, Any]:
        return {"left": self.left, "center": self.center, "right": self.right}

@dataclass
class ToggleMagnifierOrientationAction(Action):
    is_horizontal: bool

    def __init__(self, is_horizontal: bool):
        super().__init__(type=ActionType.TOGGLE_MAGNIFIER_ORIENTATION)
        self.is_horizontal = is_horizontal

    def get_payload(self) -> dict[str, Any]:
        return {"is_horizontal": self.is_horizontal}

@dataclass
class ToggleFreezeMagnifierAction(Action):
    freeze: bool
    frozen_position: Optional[QPointF] = None
    new_offset: Optional[QPointF] = None

    def __init__(self, freeze: bool, frozen_position: Optional[QPointF] = None, new_offset: Optional[QPointF] = None):
        super().__init__(type=ActionType.TOGGLE_FREEZE_MAGNIFIER)
        self.freeze = freeze
        self.frozen_position = frozen_position
        self.new_offset = new_offset

    def get_payload(self) -> dict[str, Any]:
        return {
            "freeze": self.freeze,
            "frozen_position": self.frozen_position,
            "new_offset": self.new_offset
        }

@dataclass
class SetMagnifierPositionAction(Action):
    position: QPointF

    def __init__(self, position: QPointF):
        super().__init__(type=ActionType.SET_MAGNIFIER_POSITION)
        self.position = position

    def get_payload(self) -> dict[str, Any]:
        return {"position": self.position}

@dataclass
class SetMagnifierInternalSplitAction(Action):
    split: float

    def __init__(self, split: float):
        super().__init__(type=ActionType.SET_MAGNIFIER_INTERNAL_SPLIT)
        self.split = split

    def get_payload(self) -> dict[str, Any]:
        return {"split": self.split}

@dataclass
class SetMovementSpeedAction(Action):
    speed: float

    def __init__(self, speed: float):
        super().__init__(type=ActionType.SET_MOVEMENT_SPEED)
        self.speed = speed

    def get_payload(self) -> dict[str, Any]:
        return {"speed": self.speed}

@dataclass
class UpdateMagnifierCombinedStateAction(Action):
    is_combined: bool

    def __init__(self, is_combined: bool):
        super().__init__(type=ActionType.UPDATE_MAGNIFIER_COMBINED_STATE)
        self.is_combined = is_combined

    def get_payload(self) -> dict[str, Any]:
        return {"is_combined": self.is_combined}

@dataclass
class SetIsDraggingSliderAction(Action):
    is_dragging: bool

    def __init__(self, is_dragging: bool):
        super().__init__(type=ActionType.SET_IS_DRAGGING_SLIDER)
        self.is_dragging = is_dragging

    def get_payload(self) -> dict[str, Any]:
        return {"is_dragging": self.is_dragging}

@dataclass
class SetActiveMagnifierIdAction(Action):
    magnifier_id: str

    def __init__(self, magnifier_id: str):
        super().__init__(type=ActionType.SET_ACTIVE_MAGNIFIER_ID)
        self.magnifier_id = magnifier_id

    def get_payload(self) -> dict[str, Any]:
        return {"magnifier_id": self.magnifier_id}

@dataclass
class SetDiffModeAction(Action):
    mode: str

    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_DIFF_MODE)
        self.mode = mode

    def get_payload(self) -> dict[str, Any]:
        return {"mode": self.mode}

@dataclass
class SetChannelViewModeAction(Action):
    mode: str

    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_CHANNEL_VIEW_MODE)
        self.mode = mode

    def get_payload(self) -> dict[str, Any]:
        return {"mode": self.mode}

@dataclass
class SetCachedDiffImageAction(Action):
    image: Any

    def __init__(self, image: Any):
        super().__init__(type=ActionType.SET_CACHED_DIFF_IMAGE)
        self.image = image

    def get_payload(self) -> dict[str, Any]:
        return {"image": self.image}

@dataclass
class SetDividerLineVisibleAction(Action):
    visible: bool

    def __init__(self, visible: bool):
        super().__init__(type=ActionType.SET_DIVIDER_LINE_VISIBLE)
        self.visible = visible

    def get_payload(self) -> dict[str, Any]:
        return {"visible": self.visible}

@dataclass
class SetDividerLineColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_DIVIDER_LINE_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetDividerLineThicknessAction(Action):
    thickness: int

    def __init__(self, thickness: int):
        super().__init__(type=ActionType.SET_DIVIDER_LINE_THICKNESS)
        self.thickness = thickness

    def get_payload(self) -> dict[str, Any]:
        return {"thickness": self.thickness}

@dataclass
class SetMagnifierDividerVisibleAction(Action):
    visible: bool

    def __init__(self, visible: bool):
        super().__init__(type=ActionType.SET_MAGNIFIER_DIVIDER_VISIBLE)
        self.visible = visible

    def get_payload(self) -> dict[str, Any]:
        return {"visible": self.visible}

@dataclass
class SetMagnifierDividerColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_MAGNIFIER_DIVIDER_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetMagnifierDividerThicknessAction(Action):
    thickness: int

    def __init__(self, thickness: int):
        super().__init__(type=ActionType.SET_MAGNIFIER_DIVIDER_THICKNESS)
        self.thickness = thickness

    def get_payload(self) -> dict[str, Any]:
        return {"thickness": self.thickness}

@dataclass
class SetMagnifierBorderColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_MAGNIFIER_BORDER_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetMagnifierLaserColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_MAGNIFIER_LASER_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetCaptureRingColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_CAPTURE_RING_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetMagnifierMovementInterpolationMethodAction(Action):
    method: str

    def __init__(self, method: str):
        super().__init__(type=ActionType.SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD)
        self.method = method

    def get_payload(self) -> dict[str, Any]:
        return {"method": self.method}

@dataclass
class SetLaserSmoothingInterpolationMethodAction(Action):
    method: str

    def __init__(self, method: str):
        super().__init__(type=ActionType.SET_LASER_SMOOTHING_INTERPOLATION_METHOD)
        self.method = method

    def get_payload(self) -> dict[str, Any]:
        return {"method": self.method}

@dataclass
class SetIncludeFileNamesInSavedAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_INCLUDE_FILE_NAMES_IN_SAVED)
        self.enabled = enabled

    def get_payload(self) -> dict[str, Any]:
        return {"enabled": self.enabled}

@dataclass
class SetFontSizePercentAction(Action):
    size: int

    def __init__(self, size: int):
        super().__init__(type=ActionType.SET_FONT_SIZE_PERCENT)
        self.size = size

    def get_payload(self) -> dict[str, Any]:
        return {"size": self.size}

@dataclass
class SetFontWeightAction(Action):
    weight: int

    def __init__(self, weight: int):
        super().__init__(type=ActionType.SET_FONT_WEIGHT)
        self.weight = weight

    def get_payload(self) -> dict[str, Any]:
        return {"weight": self.weight}

@dataclass
class SetTextAlphaPercentAction(Action):
    alpha: int

    def __init__(self, alpha: int):
        super().__init__(type=ActionType.SET_TEXT_ALPHA_PERCENT)
        self.alpha = alpha

    def get_payload(self) -> dict[str, Any]:
        return {"alpha": self.alpha}

@dataclass
class SetFileNameColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_FILE_NAME_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetFileNameBgColorAction(Action):
    color: QColor

    def __init__(self, color: QColor):
        super().__init__(type=ActionType.SET_FILE_NAME_BG_COLOR)
        self.color = color

    def get_payload(self) -> dict[str, Any]:
        return {"color": self.color}

@dataclass
class SetDrawTextBackgroundAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_DRAW_TEXT_BACKGROUND)
        self.enabled = enabled

    def get_payload(self) -> dict[str, Any]:
        return {"enabled": self.enabled}

@dataclass
class SetTextPlacementModeAction(Action):
    mode: str

    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_TEXT_PLACEMENT_MODE)
        self.mode = mode

    def get_payload(self) -> dict[str, Any]:
        return {"mode": self.mode}

@dataclass
class SetCurrentIndexAction(Action):
    slot: int
    index: int

    def __init__(self, slot: int, index: int):
        super().__init__(type=ActionType.SET_CURRENT_INDEX)
        self.slot = slot
        self.index = index

    def get_payload(self) -> dict[str, Any]:
        return {"slot": self.slot, "index": self.index}

@dataclass
class SetOriginalImageAction(Action):
    slot: int
    image: Any

    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_ORIGINAL_IMAGE)
        self.slot = slot
        self.image = image

    def get_payload(self) -> dict[str, Any]:
        return {"slot": self.slot, "image": self.image}

@dataclass
class SetFullResImageAction(Action):
    slot: int
    image: Any

    def __init__(self, slot: int, image: Any):
        super().__init__(type=ActionType.SET_FULL_RES_IMAGE)
        self.slot = slot
        self.image = image

    def get_payload(self) -> dict[str, Any]:
        return {"slot": self.slot, "image": self.image}

@dataclass
class SetImagePathAction(Action):
    slot: int
    path: str

    def __init__(self, slot: int, path: str):
        super().__init__(type=ActionType.SET_IMAGE_PATH)
        self.slot = slot
        self.path = path

    def get_payload(self) -> dict[str, Any]:
        return {"slot": self.slot, "path": self.path}

@dataclass
class SetLanguageAction(Action):
    language: str

    def __init__(self, language: str):
        super().__init__(type=ActionType.SET_LANGUAGE)
        self.language = language

    def get_payload(self) -> dict[str, Any]:
        return {"language": self.language}

@dataclass
class SetUIModeAction(Action):
    mode: str

    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_UI_MODE)
        self.mode = mode

    def get_payload(self) -> dict[str, Any]:
        return {"mode": self.mode}

@dataclass
class SetAutoCropBlackBordersAction(Action):
    enabled: bool

    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_AUTO_CROP_BLACK_BORDERS)
        self.enabled = enabled

    def get_payload(self) -> dict[str, Any]:
        return {"enabled": self.enabled}

@dataclass
class InvalidateRenderCacheAction(Action):

    def __init__(self):
        super().__init__(type=ActionType.INVALIDATE_RENDER_CACHE)

    def get_payload(self) -> dict[str, Any]:
        return {}

@dataclass
class InvalidateGeometryCacheAction(Action):

    def __init__(self):
        super().__init__(type=ActionType.INVALIDATE_GEOMETRY_CACHE)

    def get_payload(self) -> dict[str, Any]:
        return {}

@dataclass
class ClearAllCachesAction(Action):

    def __init__(self):
        super().__init__(type=ActionType.CLEAR_ALL_CACHES)

    def get_payload(self) -> dict[str, Any]:
        return {}

@dataclass
class ClearImageSlotDataAction(Action):
    slot: int

    def __init__(self, slot: int):
        super().__init__(type=ActionType.CLEAR_IMAGE_SLOT_DATA)
        self.slot = slot

    def get_payload(self) -> dict[str, Any]:
        return {"slot": self.slot}

