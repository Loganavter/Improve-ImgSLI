from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_dragdrop_service, get_flyout_timings, resolve_overlay_layer
from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel
from ui.widgets.unified_list_picker.common import (
    FlyoutMode,
    _RoundedClipEffect,
)
from ui.widgets.unified_list_picker.session import (
    _UnifiedFlyoutSessionMixin,
)
from ui.widgets.unified_list_picker.surface import (
    FlyoutSurfaceWidget,
    pin_scroll_area_transparency,
)

class _UnifiedFlyoutBootstrapMixin(_UnifiedFlyoutSessionMixin):

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
        self._structure_sync_scheduled = False
        self._drag_enabled = True
        # The picker re-anchors itself on every refresh (showAsSingle /
        # refreshGeometry re-read the anchor combos); FlyoutManager's
        # anchor-move auto-close would fire on unrelated layout reflows
        # (e.g. a rating display label becoming visible shifts the toolbar),
        # so opt out of it — passive outside-click dismissal still applies.
        self.close_on_anchor_move = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_geometry)
        self.flyout_manager = FlyoutManager.get_instance()
        self.flyout_manager.register_flyout(self)
        self._anchor_left: QWidget | None = None
        self._anchor_right: QWidget | None = None
        timings = get_flyout_timings()
        self._move_duration_ms = timings.flyout_animation_duration_ms
        self._drop_offset_px = timings.dropdown_drop_offset_px

    def _initialize_widget(self):
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _attach_overlay_layer(self):
        self.overlay_layer = resolve_overlay_layer(self.main_window)
        if self.overlay_layer is not None:
            self.overlay_layer.attach(self)

    def _initialize_components(self):
        self._init_container_and_panels()
        self._init_clipping()
        self._init_drag_drop()
        self._init_theme()

    def _init_container_and_panels(self):
        # FlyoutSurfaceWidget paints the container chrome (flyout tokens,
        # 1px border, scaled radius) in paintEvent — the retired
        # `QWidget#FlyoutWidget` QSS rules could not survive the migration
        # because app QSS backgrounds no-op on custom QWidget subclasses.
        # WA_StyledBackground is unnecessary with an explicit paintEvent.
        self.container_widget = FlyoutSurfaceWidget(self)
        self.container_widget.setObjectName("FlyoutWidget")
        self.container_widget.setProperty("surfaceRole", "container")
        self.panel_left = self._create_panel(1)
        self.panel_right = self._create_panel(2)
        # QScrollArea.setWidget flips autoFillBackground on for viewports and
        # content widgets; pin them transparent so no Base-colored rectangle
        # covers the painted surface (replaces the retired
        # `QWidget#FlyoutWidget QScrollArea` QSS rule).
        pin_scroll_area_transparency(self.container_widget)

    def _document(self):
        """Current document via the host store's session-state slot API.

        Generic fallback (own-attribute stores like
        ``SimpleUnifiedFlyoutStore``) keeps the picker usable standalone.
        """
        try:
            getter = self.store.get_session_state_slot
        except Exception:
            getter = None
        if callable(getter):
            try:
                return getter("document")
            except Exception:
                pass
        # Standalone stores (SimpleUnifiedFlyoutStore) keep their own DTO.
        return getattr(self.store, "doc", None) or getattr(self.store, "document", None)

    def set_row_factory(self, factory) -> None:
        """Host rows: replace the panels' row factory (e.g. a rating row).

        Rows are built per open (populate), so setting this after
        construction is safe — the next show uses the new factory.
        """
        self.panel_left.set_row_factory(factory)
        self.panel_right.set_row_factory(factory)

    def _create_panel(self, list_num: int) -> ListPanel:
        return ListPanel(
            list_num,
            self.item_height,
            self.item_font,
            self._get_current_index,
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

    def _init_drag_drop(self):
        service = get_dragdrop_service()
        if service is not None:
            service.register_drop_target(self)
        self.destroyed.connect(self._on_destroyed)

    def _init_theme(self):
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()

    def _on_destroyed(self):
        try:
            service = get_dragdrop_service()
            if service is not None:
                service.unregister_drop_target(self)
        except Exception:
            pass
        try:
            self.flyout_manager.unregister_flyout(self)
        except Exception:
            pass

    def contains_global(self, global_pos) -> bool:
        if not self.isVisible():
            return False
        try:
            if self.overlay_layer is not None and hasattr(
                self.overlay_layer, "contains_global"
            ):
                return self.overlay_layer.contains_global(self, global_pos)
            return self.rect().contains(self.mapFromGlobal(global_pos))
        except RuntimeError:
            return False

    def anchor_contains_global(self, global_pos) -> bool:
        for anchor in self.anchor_widgets():
            try:
                top_left = anchor.mapToGlobal(QPoint(0, 0))
                if QRect(top_left, anchor.size()).contains(global_pos):
                    return True
            except RuntimeError:
                continue
        return False

    def set_list_anchors(
        self,
        left: QWidget | None,
        right: QWidget | None,
    ) -> None:
        """Register the two list anchor widgets used for geometry and open state."""
        self._anchor_left = left
        self._anchor_right = right

    def anchor_for_list(self, list_num: int) -> QWidget | None:
        if list_num == 1:
            return self._anchor_left
        if list_num == 2:
            return self._anchor_right
        return getattr(self, "_anchor_widget", None)

    def anchor_widgets(self) -> tuple[QWidget, ...]:
        anchors = tuple(
            anchor
            for anchor in (self._anchor_left, self._anchor_right)
            if isinstance(anchor, QWidget)
        )
        if anchors:
            return anchors
        anchor = getattr(self, "_anchor_widget", None)
        return (anchor,) if isinstance(anchor, QWidget) else ()