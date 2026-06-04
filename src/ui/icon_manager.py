from enum import Enum
from pathlib import Path

from PyQt6.QtGui import QIcon

from events.drag_drop_handler import DragAndDropService
import resources.translations  # noqa: F401  — triggers i18n_root configuration
from shared_toolkit.ui.gesture_resolver import RatingGestureTransaction
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.icons import configure_icon_resolver, get_icon_service
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    LabelVariantSpec,
    register_label_variant,
)
from sli_ui_toolkit.ui.widgets.buttons._dropdown_menu import DropdownMenu

DropdownMenu.APPEAR_EXTRA_Y = 12

register_label_variant(
    LabelVariantSpec("group-title", pixel_size=14, bold=False, color_token="dialog.text", elide=True)
)

class AppIcon(Enum):
    SETTINGS = "settings.svg"
    SAVE = "save_icon.svg"
    QUICK_SAVE = "quick_save.svg"
    HELP = "help.svg"
    PHOTO = "photo_icon.svg"
    SYNC = "sync.svg"
    DELETE = "delete.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    VERTICAL_SPLIT = "vertical_split.svg"
    HORIZONTAL_SPLIT = "horizontal_split.svg"
    MAGNIFIER = "magnifier.svg"
    FREEZE = "freeze.svg"
    TEXT_FILENAME = "text_filename.svg"
    HIGHLIGHT_DIFFERENCES = "highlight_diff_icon.svg"
    DIVIDER_VISIBLE = "divider_visible.svg"
    DIVIDER_HIDDEN = "divider_hidden.svg"
    DIVIDER_COLOR = "divider_color.svg"
    DIVIDER_WIDTH = "divider_width.svg"
    ADD = "add.svg"
    ADD_CIRCLE = "add_circle.svg"
    REMOVE = "remove.svg"
    CHECK = "check.svg"

    RECORD = "record.svg"
    STOP = "stop.svg"
    PAUSE = "pause.svg"
    PLAY = "play.svg"
    EXPORT_VIDEO = "video.svg"
    VIDEO_EDIT = "edit_video.svg"
    UNDO = "undo.svg"
    REDO = "redo.svg"
    SCISSORS = "scissors.svg"
    CROP_IN = "crop_in.svg"
    CROP_OUT = "crop_out.svg"

    LINK = "link.svg"
    UNLINK = "unlink.svg"
    MAGNIFIER_GUIDES = "laser.svg"
    CAPTURE_AREA_COLOR = "circle_outline.svg"
    MAGNIFIER_BORDER_COLOR = "magnifier.svg"

def get_app_icon(icon: AppIcon | str) -> QIcon:
    project_root = Path(__file__).resolve().parents[1]
    service = get_icon_service("Improve-ImgSLI", project_root=str(project_root))
    if isinstance(icon, AppIcon):
        return service.get_icon(icon.value)
    if isinstance(icon, str):
        return service.get_icon(icon)
    value = getattr(icon, "value", None)
    if isinstance(value, str):
        return service.get_icon(value)
    return QIcon()

configure_icon_resolver(
    get_app_icon,
    named_icons={
        "divider_hidden": AppIcon.DIVIDER_HIDDEN,
        "magnifier": AppIcon.MAGNIFIER,
        "add": AppIcon.ADD,
        "add_circle": AppIcon.ADD_CIRCLE,
        "remove": AppIcon.REMOVE,
        "check": AppIcon.CHECK,
    },
)

configure_toolkit(
    timings=FlyoutTimingConfig(
        transient_auto_hide_delay_ms=300,
        flyout_animation_duration_ms=80,
        text_settings_flyout_animation_duration_ms=80,
    ),
    overlay_resolver=get_overlay_layer,
    rating_gesture_factory=lambda **kwargs: RatingGestureTransaction(**kwargs),
    dragdrop_service_getter=DragAndDropService.get_instance,
)

