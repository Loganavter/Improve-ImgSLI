from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_flyout_timings
from .bootstrap import _UnifiedFlyoutBootstrapMixin
from .common import FlyoutMode
from .content import _UnifiedFlyoutContentMixin
from .dragdrop import _UnifiedFlyoutDragDropMixin
from .layout import _UnifiedFlyoutLayoutMixin
from .refresh import _UnifiedFlyoutRefreshMixin
from .style import _UnifiedFlyoutStyleMixin

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

    _move_duration_ms = get_flyout_timings().flyout_animation_duration_ms

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
