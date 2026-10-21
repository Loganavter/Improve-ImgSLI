from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.icons import IconService, get_icon_by_name, get_icon_service
from sli_ui_toolkit.utils import get_unique_filepath, resource_path

from sli_ui_toolkit.widgets import (
    MINIMAL_SCROLLBAR_WIDTH,
    Button,
    CheckBox,
    ComboBox,
    CustomGroupBuilder,
    CustomGroupWidget,
    CustomLineEdit,
    MinimalistScrollBar,
    OverlayScrollArea,
    RadioButton,
    Slider,
    SpinBox,
    Switch,
    overlay_scrollbar_max_inset,
)
# `Label` left the public surface in text 2b (toolkit #97); the class lives on
# as a documented internal exception until the three Text-capability tickets
# close. Re-exported here for the app's remaining consumers.
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

__version__ = "1.1.0"
__author__ = "Loganavter"

__all__ = [
    "get_unique_filepath",
    "resource_path",
    "CheckBox",
    "ComboBox",
    "CustomLineEdit",
    "RadioButton",
    "Switch",
    "Slider",
    "SpinBox",
    "Label",
    "CustomGroupWidget",
    "CustomGroupBuilder",
    "MinimalistScrollBar",
    "OverlayScrollArea",
    "MINIMAL_SCROLLBAR_WIDTH",
    "overlay_scrollbar_max_inset",
    "ThemeManager",
    "FlyoutManager",
    "IconService",
    "get_icon_by_name",
    "get_icon_service",
]
