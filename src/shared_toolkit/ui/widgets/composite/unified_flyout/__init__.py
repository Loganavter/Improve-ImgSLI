from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from core.constants import AppConstants
from shared_toolkit.ui.widgets.composite.unified_flyout.bootstrap import (
    _UnifiedFlyoutBootstrapMixin,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode
from shared_toolkit.ui.widgets.composite.unified_flyout.content import (
    _UnifiedFlyoutContentMixin,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.dragdrop import (
    _UnifiedFlyoutDragDropMixin,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.layout import (
    _UnifiedFlyoutLayoutMixin,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.refresh import (
    _UnifiedFlyoutRefreshMixin,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.style import (
    _UnifiedFlyoutStyleMixin,
)

__all__ = ["FlyoutMode", "UnifiedFlyout"]

class UnifiedFlyout(
    _UnifiedFlyoutBootstrapMixin,
    _UnifiedFlyoutStyleMixin,
    _UnifiedFlyoutLayoutMixin,
    _UnifiedFlyoutRefreshMixin,
    _UnifiedFlyoutContentMixin,
    _UnifiedFlyoutDragDropMixin,
    QWidget,
):
    item_chosen = pyqtSignal(int, int)
    simple_item_chosen = pyqtSignal(int)
    closing_animation_finished = pyqtSignal()

    SHADOW_RADIUS = 10
    MARGIN = 0
    SINGLE_APPEAR_EXTRA_Y = 8
    DOUBLE_CONTENT_EXTRA_Y = 8

    _move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS

    def __init__(self, store, main_controller, main_window):
        super().__init__(main_window)
        self.store = store
        self.main_controller = main_controller
        self.main_window = main_window

        self._initialize_runtime_state()
        self._initialize_widget()
        self._attach_overlay_layer()
        self._initialize_components()
        self.hide()
