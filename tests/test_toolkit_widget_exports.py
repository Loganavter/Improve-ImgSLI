from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "packages",
        "sli-ui-toolkit",
        "src",
    ),
)

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
