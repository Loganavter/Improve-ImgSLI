from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.icons import IconService, get_icon_by_name, get_icon_service
from sli_ui_toolkit.utils import get_unique_filepath, resource_path

# Documented exception (text-unification wave C): Label is no longer a public
# export; the class still lives on the internal module until step 2c. Import
# from there and keep the re-export so app callers do not break in this release.
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

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
