"""Image-compare tab icon registry."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)


class Icon(Enum):
    PHOTO = "photo_icon.svg"
    SYNC = "sync.svg"
    DELETE = "delete.svg"
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
    MAGNIFIER_GUIDES = "laser.svg"
    CAPTURE_AREA_COLOR = "circle_outline.svg"
    MAGNIFIER_BORDER_COLOR = "magnifier.svg"
    SETTINGS = "settings.svg"
    HELP = "help.svg"
    TEXT_MANIPULATOR = "text-manipulator.svg"
    QUICK_SAVE = "quick_save.svg"
    SAVE = "save_icon.svg"
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
    COPY = "copy.svg"
    ADD = "add.svg"
