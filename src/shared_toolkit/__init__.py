from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.icons import IconService, get_icon_by_name, get_icon_service
from sli_ui_toolkit.utils import get_unique_filepath, resource_path

from sli_ui_toolkit.widgets import (
    AdaptiveLabel,
    BodyLabel,
    ButtonMode,
    CaptionLabel,
    CheckBox,
    ComboBox,
    CompactLabel,
    CustomButton,
    CustomGroupBuilder,
    CustomGroupWidget,
    CustomLineEdit,
    GroupTitleLabel,
    MinimalistScrollBar,
    OverlayScrollArea,
    RadioButton,
    Slider,
    SpinBox,
    Switch,
    UnifiedIconButton,
)

FluentCheckBox = CheckBox
FluentComboBox = ComboBox
FluentRadioButton = RadioButton
FluentSlider = Slider
FluentSpinBox = SpinBox
FluentSwitch = Switch

__version__ = "1.1.0"
__author__ = "Loganavter"

__all__ = [
    "get_unique_filepath",
    "resource_path",
    "CheckBox",
    "ComboBox",
    "CustomButton",
    "CustomLineEdit",
    "RadioButton",
    "Switch",
    "Slider",
    "SpinBox",
    "BodyLabel",
    "CaptionLabel",
    "AdaptiveLabel",
    "CompactLabel",
    "GroupTitleLabel",
    "CustomGroupWidget",
    "CustomGroupBuilder",
    "MinimalistScrollBar",
    "OverlayScrollArea",
    "UnifiedIconButton",
    "ButtonMode",
    "ThemeManager",
    "FlyoutManager",
    "IconService",
    "get_icon_by_name",
    "get_icon_service",

    "FluentCheckBox",
    "FluentComboBox",
    "FluentRadioButton",
    "FluentSlider",
    "FluentSpinBox",
    "FluentSwitch",
]
