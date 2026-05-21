from sli_ui_toolkit.ui.widgets.atomic.clickable_label import ClickableLabel
from sli_ui_toolkit.ui.widgets.atomic.custom_group_widget import (
    CustomGroupBuilder,
    CustomGroupWidget,
)
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.atomic.drop_zone_label import DropZoneLabel
from sli_ui_toolkit.ui.widgets.atomic.checkbox import CheckBox, FluentCheckBox
from sli_ui_toolkit.ui.widgets.atomic.combobox import ComboBox, FluentComboBox
from sli_ui_toolkit.ui.widgets.atomic.radio import FluentRadioButton, RadioButton
from sli_ui_toolkit.ui.widgets.atomic.slider import FluentSlider, Slider
from sli_ui_toolkit.ui.widgets.atomic.switch import FluentSwitch, Switch
from sli_ui_toolkit.ui.widgets.atomic.spinbox import FluentSpinBox, SpinBox
from sli_ui_toolkit.ui.widgets.atomic.loading_spinner import LoadingSpinner
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MinimalistScrollBar,
    OverlayScrollArea,
)
from sli_ui_toolkit.ui.widgets.atomic.instances_counter_button import (
    InstancesCounterButton,
    MagnifierInstancesButton,
)
from sli_ui_toolkit.ui.widgets.atomic.comboboxes import ScrollableComboBox
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    AdaptiveLabel,
    BodyLabel,
    CaptionLabel,
    CompactLabel,
    GroupTitleLabel,
)
from sli_ui_toolkit.ui.widgets.atomic.time_line_edit import TimeLineEdit

from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonGroup
from sli_ui_toolkit.ui.widgets.buttons._painter import ButtonPainter

ButtonGroupContainer = ButtonGroup
IconButton = Button
SimpleIconButton = Button
ToggleIconButton = Button
ScrollableIconButton = Button
ToggleScrollableIconButton = Button
CustomButton = Button
ToolButton = Button
ToolButtonWithMenu = Button
UnifiedIconButton = Button
NumberedToggleIconButton = Button
LongPressIconButton = Button
AutoRepeatButton = Button

class ButtonType:
    """Compat stub — no longer used."""
    pass

class ButtonMode:
    """Compat stub — no longer used."""
    pass

__all__ = [
    "AdaptiveLabel",
    "AutoRepeatButton",
    "BodyLabel",
    "ButtonGroupContainer",
    "ButtonMode",
    "ButtonPainter",
    "ButtonType",
    "CaptionLabel",
    "ClickableLabel",
    "CompactLabel",
    "CustomButton",
    "CustomGroupBuilder",
    "CustomGroupWidget",
    "CustomLineEdit",
    "DropZoneLabel",
    "CheckBox",
    "ComboBox",
    "FluentCheckBox",
    "FluentComboBox",
    "FluentRadioButton",
    "FluentSlider",
    "FluentSpinBox",
    "FluentSwitch",
    "RadioButton",
    "Slider",
    "SpinBox",
    "Switch",
    "GroupTitleLabel",
    "IconButton",
    "LoadingSpinner",
    "LongPressIconButton",
    "InstancesCounterButton",
    "MagnifierInstancesButton",
    "MinimalistScrollBar",
    "OverlayScrollArea",
    "NumberedToggleIconButton",
    "ScrollableComboBox",
    "ScrollableIconButton",
    "SimpleIconButton",
    "TimeLineEdit",
    "ToggleIconButton",
    "ToggleScrollableIconButton",
    "ToolButton",
    "ToolButtonWithMenu",
    "UnifiedIconButton",
]
