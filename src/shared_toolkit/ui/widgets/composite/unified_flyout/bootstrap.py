from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QWidget

from core.constants import AppConstants
from events.drag_drop_handler import DragAndDropService
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from shared_toolkit.ui.widgets.composite.unified_flyout.common import (
    FlyoutMode,
    _RoundedClipEffect,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.panel import (
    _ListOwnerProxy,
    _Panel,
)
from shared_toolkit.ui.widgets.composite.unified_flyout.session import (
    _UnifiedFlyoutSessionMixin,
)

class _UnifiedFlyoutBootstrapMixin(_UnifiedFlyoutSessionMixin):
    _move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS

    def _initialize_runtime_state(self):
        self.mode = FlyoutMode.HIDDEN
        self.source_list_num = 1
        self._is_closing = False
        self.item_height = 36
        self.item_font = None
        self.last_close_timestamp = 0.0
        self.last_close_mode = FlyoutMode.HIDDEN
        self._anim = None
        self._is_simple_mode = False
        self._is_refreshing = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_geometry)

    def _initialize_widget(self):
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _attach_overlay_layer(self):
        self.overlay_layer = get_overlay_layer(self.main_window)
        if self.overlay_layer is not None:
            self.overlay_layer.attach(self)

    def _initialize_components(self):
        self._init_container_and_panels()
        self._init_clipping()
        self._init_owner_proxies()
        self._init_drag_drop()
        self._init_theme()

    def _init_container_and_panels(self):
        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("FlyoutWidget")
        self.container_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.container_widget.setProperty("surfaceRole", "container")
        self.panel_left = self._create_panel(1)
        self.panel_right = self._create_panel(2)

    def _create_panel(self, image_number: int) -> _Panel:
        return _Panel(
            image_number,
            self.item_height,
            self.item_font,
            self._get_current_index,
            self._get_item_rating,
            self._increment_rating,
            self._decrement_rating,
            self._create_rating_gesture,
            self._on_item_selected,
            self._on_item_right_clicked,
            self._reorder_item,
            self._move_item_between_lists,
            self.update_drop_indicator,
            self.clear_drop_indicator,
            self.container_widget,
        )

    def _init_clipping(self):
        self._container_clip = _RoundedClipEffect(8, self.container_widget)
        self.container_widget.setGraphicsEffect(self._container_clip)
        self._panel_left_clip = _RoundedClipEffect(8, self.panel_left)
        self.panel_left.setGraphicsEffect(self._panel_left_clip)
        self._panel_right_clip = _RoundedClipEffect(8, self.panel_right)
        self.panel_right.setGraphicsEffect(self._panel_right_clip)

    def _init_owner_proxies(self):
        self._owner_proxy_left = _ListOwnerProxy(1)
        self._owner_proxy_right = _ListOwnerProxy(2)
        self._owner_proxy_simple = _ListOwnerProxy(0)

    def _init_drag_drop(self):
        DragAndDropService.get_instance().register_drop_target(self)
        self.destroyed.connect(self._on_destroyed)

    def _init_theme(self):
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()

    def _on_destroyed(self):
        try:
            DragAndDropService.get_instance().unregister_drop_target(self)
        except Exception:
            pass
