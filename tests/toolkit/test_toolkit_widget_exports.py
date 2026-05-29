"""Public toolkit exports exist (generic widgets, ColorOptionsFlyout) and keep
backward-compatible names (InstancesCounter).

Dogma source: docs/dev/UI_TOOLKIT_LIBRARY.md.
"""

from __future__ import annotations
from sli_ui_toolkit.ui.widgets.composite import (
    ColorOptionsFlyout,
    FlyoutIconButton,
    IconActionFlyout,
    IndexedToggleFlyout,
)
from sli_ui_toolkit.ui.widgets.atomic import (
    InstancesCounterButton,
    MagnifierInstancesButton,
)

def test_toolkit_generic_exports_exist():
    assert FlyoutIconButton is not None
    assert IndexedToggleFlyout is not None
    assert InstancesCounterButton is not None

def test_color_options_flyout_is_icon_action_flyout():
    assert ColorOptionsFlyout is IconActionFlyout

def test_instances_counter_backward_compat():
    assert MagnifierInstancesButton is InstancesCounterButton
