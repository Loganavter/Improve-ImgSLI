from sli_ui_toolkit.managers import FlyoutManager

from .managers import ThemeManager
from .services import IconService, get_icon_by_name, get_icon_service
from sli_ui_toolkit.widgets import (
    AdaptiveLabel,
    BodyLabel,
    Button,
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

__all__ = [
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
