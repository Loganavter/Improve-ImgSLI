

from enum import Enum
from PyQt6.QtGui import QIcon

from toolkit.services import get_icon_service

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

def get_app_icon(icon: AppIcon) -> QIcon:
    service = get_icon_service("Improve-ImgSLI")
    return service.get_icon(icon.value)
