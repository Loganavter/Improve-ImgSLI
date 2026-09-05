from ui.widgets.unified_list_picker.debug import double_geom_debug

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.managers.ui_font import paint_font, rebase_family, ui_font
from ui.widgets.unified_list_picker.common import (
    FlyoutMode,
    ListItemType,
    _UnifiedFlyoutBase,
    items_for_list,
)
from ui.widgets.unified_list_picker.double_geometry import (
    compute_double_mode_geometry,
    ensure_double_mode_scroll_behavior,
    resolve_double_mode_top,
    sync_double_mode_button_state,
)

class _UnifiedFlyoutLayoutMixin(_UnifiedFlyoutBase):
    mode: FlyoutMode
    _move_easing = QEasingCurve.Type.OutQuad

    def _dbg_rect(self, rect) -> str:
        try:
            return f"({rect.x()},{rect.y()},{rect.width()}x{rect.height()})"
        except Exception:
            return "?"

    def showAsSingle(
        self,
        list_num: int,
        anchor_widget: QWidget,
        list_type: ListItemType = "image",
        simple_items=None,
        simple_current_index=-1,
    ):
        requested_mode = (
            FlyoutMode.SINGLE_SIMPLE
            if list_type == "simple"
            else (FlyoutMode.SINGLE_LEFT if list_num == 1 else FlyoutMode.SINGLE_RIGHT)
        )
        if self.isVisible() and self.mode == FlyoutMode.DOUBLE:
            self.start_closing_animation()
            return
        if self.isVisible() and self.mode == requested_mode:
            self.start_closing_animation()
            return

        self._anchor_widget = anchor_widget
        self.flyout_manager.request_show(self)
        if self._anim:
            self._anim.stop()

        self.source_list_num = list_num
        self._is_simple_mode = list_type == "simple"
        self._set_single_mode(list_num)
        self._apply_style()
        self.item_height = getattr(anchor_widget, "getItemHeight", lambda: 34)()
        getter = getattr(anchor_widget, "getItemFont", None)
        raw = getter() if callable(getter) else None
        # Anchor metrics are live (already scale-resolved: getItemHeight is the
        # button's real height, getItemFont is paint_font) — normalize the
        # family only, never re-scale, or rows blow up ~factor^2/factor^3.
        self.item_font = (
            rebase_family(raw) if raw is not None else paint_font(anchor_widget)
        )
        active_list_num = self._populate_for_single_mode(
            list_num, simple_items, simple_current_index
        )
        self._sync_anchor_open_state(list_num)
        ideal_geom, start_pos, end_pos = self._build_single_mode_geometry(
            anchor_widget, active_list_num
        )
        self.resize(ideal_geom.size())
        self.move(start_pos)
        self._apply_container_geometry()
        self._position_panels_for_single()
        self.show()
        self.raise_()
        self._start_show_animation(start_pos, end_pos)

    def _sync_anchor_open_state(self, open_list_num: int | None) -> None:
        for list_num in (1, 2):
            anchor = self.anchor_for_list(list_num)
            if anchor is not None and hasattr(anchor, "setFlyoutOpen"):
                anchor.setFlyoutOpen(
                    open_list_num is not None and list_num == open_list_num
                )

    def _set_single_mode(self, list_num: int):
        if self._is_simple_mode:
            self.mode = FlyoutMode.SINGLE_SIMPLE
        else:
            self.mode = (
                FlyoutMode.SINGLE_LEFT if list_num == 1 else FlyoutMode.SINGLE_RIGHT
            )

    def _populate_for_single_mode(
        self, list_num: int, simple_items, simple_current_index: int
    ) -> int:
        if self._is_simple_mode:
            self.populate(
                0, simple_items, list_type="simple", current_index=simple_current_index
            )
            self.panel_left.show()
            self.panel_right.hide()
            return 1
        self.populate(1, items_for_list(self._document(), 1))
        self.populate(2, items_for_list(self._document(), 2))
        self.panel_left.setVisible(list_num == 1)
        self.panel_right.setVisible(list_num == 2)
        return list_num

    def _build_single_mode_geometry(
        self, anchor_widget: QWidget, active_list_num: int
    ) -> tuple[QRect, QPoint, QPoint]:
        active_panel = self.panel_left if active_list_num == 1 else self.panel_right
        panel_size = self._calc_panel_total_size(active_list_num)
        content_rect = self._calculate_ideal_content_geometry(
            anchor_widget, panel_size
        )
        content_rect = self._fit_single_panel_content_rect(
            anchor_widget,
            active_panel,
            content_rect,
        )
        ideal_geom = self._outer_from_content_rect(content_rect)
        final_geom = self._clamp_outer_rect(ideal_geom, allow_resize=False)
        end_pos = final_geom.topLeft()
        requested_start_pos = QPoint(end_pos.x(), end_pos.y() - self._drop_offset_px)
        start_rect = self._clamp_outer_rect(
            QRect(
                requested_start_pos,
                final_geom.size(),
            )
        )
        start_pos = (
            start_rect.topLeft()
            if start_rect.topLeft() == requested_start_pos
            else end_pos
        )
        return final_geom, start_pos, end_pos

    def _fit_single_panel_content_rect(
        self,
        anchor_widget: QWidget,
        panel,
        preferred: QRect,
    ) -> QRect:
        y, height = self._resolve_content_y_and_height(
            anchor_widget,
            preferred.y(),
            panel._container_height,
            panel,
        )
        if height < panel._container_height:
            panel.recalculate_and_set_height(max_height=height)
            y, height = self._resolve_content_y_and_height(
                anchor_widget,
                preferred.y(),
                panel._container_height,
                panel,
            )
        return QRect(preferred.x(), y, preferred.width(), height)

    def _minimum_scrollable_panel_height(self, panel) -> int:
        row_h = self.item_height if self.item_height > 0 else getattr(panel, "item_height", 36)
        if row_h <= 0:
            row_h = 36
        spacing = 0
        try:
            spacing = panel.content_layout.spacing()
        except Exception:
            pass
        return max(1, (row_h * 2) + spacing + 10)

    def _resolve_content_y_and_height(
        self,
        anchor_widget: QWidget,
        preferred_y: int,
        natural_height: int,
        panel,
    ) -> tuple[int, int]:
        outer_available = surface_available_rect(self, anchor_widget, self.overlay_layer)
        available = outer_available.adjusted(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
        )
        if available.height() < 1 or available.width() < 1:
            available = outer_available
        anchor_rect = surface_anchor_rect(self, anchor_widget, self.overlay_layer)
        natural_height = max(1, int(natural_height))
        min_scroll_height = min(
            natural_height,
            self._minimum_scrollable_panel_height(panel),
        )

        # Invariant: when the panel fits below the anchor, the content top is
        # exactly anchor.bottom + SINGLE_PANEL_GAP_Y (never shifted upward);
        # the outer widget top is then content_top - SHADOW_RADIUS, symmetric
        # with _apply_container_geometry (the inverse adjusted()).
        below_y = preferred_y
        below_space = available.bottom() - below_y + 1
        if below_space >= min_scroll_height:
            return below_y, min(natural_height, max(1, below_space))

        above_space = anchor_rect.top() - self.SINGLE_PANEL_GAP_Y - available.top()
        if above_space >= min_scroll_height:
            height = min(natural_height, max(1, above_space))
            return anchor_rect.top() - self.SINGLE_PANEL_GAP_Y - height, height

        height = min(natural_height, max(1, available.height()))
        y = preferred_y
        if y + height - 1 > available.bottom():
            y = available.bottom() - height + 1
        if y < available.top():
            y = available.top()
        return y, height

    def _outer_from_content_rect(self, content_rect: QRect) -> QRect:
        return content_rect.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )

    def _content_height_from_outer(self, outer_rect: QRect) -> int:
        return max(1, outer_rect.height() - self.SHADOW_RADIUS * 2)

    def _clamp_outer_rect(self, outer_rect: QRect, *, allow_resize: bool = False) -> QRect:
        available = surface_available_rect(
            self,
            self.main_window if isinstance(self.main_window, QWidget) else None,
            self.overlay_layer,
        )
        # The outer rect includes a SHADOW_RADIUS halo on each side that is
        # purely decorative; allowing it to extend past the available area
        # keeps the content rect aligned with its anchor.
        shadow_expanded = available.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        return clamp_surface_rect(outer_rect, shadow_expanded, allow_resize=allow_resize)

    def _start_show_animation(self, start_pos: QPoint, end_pos: QPoint):
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(self._move_duration_ms)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(end_pos)
        self._anim.setEasingCurve(self._move_easing)
        self._anim.finished.connect(self._on_animation_finished)
        self._anim.start()

    def switchToDoubleMode(self):
        double_geom_debug(
            "switchToDouble mode=%s visible=%s simple=%s "
            "anchors l=%s r=%s",
            getattr(self.mode, "name", self.mode),
            self.isVisible(),
            self._is_simple_mode,
            "ok" if self._anchor_left is not None else None,
            "ok" if self._anchor_right is not None else None,
        )
        if (
            self.mode == FlyoutMode.DOUBLE
            or not self.isVisible()
            or self._is_simple_mode
        ):
            return

        # Interrupted show animations rest at start_pos (above end): tear the
        # animation down now; the double geometry below snaps to end_pos.
        anim, self._anim = self._anim, None
        end_pos = None
        if anim is not None:
            try:
                end_pos = anim.endValue()
                if anim.state() == QPropertyAnimation.State.Running:
                    anim.stop()
                anim.finished.disconnect(self._on_animation_finished)
            except (RuntimeError, TypeError):
                pass
            try:
                anim.deleteLater()
            except RuntimeError:
                pass

        self.mode = FlyoutMode.DOUBLE
        self.panel_left.show()
        self.panel_right.show()
        self._sync_anchor_open_state(None)
        self._apply_style()
        self._update_geometry_in_double_mode_internal()
        if end_pos is not None and (
            self._anchor_left is None or self._anchor_right is None
        ):
            # _update_geometry_in_double_mode_internal early-returns without
            # both anchors — still snap to end, never to the start_pos above.
            self.move(end_pos)
        self.raise_()

    def _apply_panel_geometries(self, local1: QRect, local2: QRect):
        double_geom_debug(
            "apply req p1=%s p2=%s cont=%s",
            self._dbg_rect(local1),
            self._dbg_rect(local2),
            self._dbg_rect(self.container_widget.rect()),
        )
        # DOUBLE mode computes equal-height panel rects, but each panel still
        # carries the stale single-mode min/max clamp (natural height of its
        # own list). Qt silently clamps setGeometry to maximumHeight, so the
        # shorter panel never grows: panels end up asymmetric (e.g. 154 vs 82)
        # and — worse — the unchanged size emits no Resize event, so the
        # virtual-list controller never rebinds and rows stay frozen at the
        # hidden-panel width, huddled top-left. Relax the stale limits first
        # (grow-only), then rebind synchronously so row widths settle without
        # waiting on deferred resize/scrollbar timers mid-drag.
        self._relax_panel_limits_for_double(self.panel_left, local1.height())
        self._relax_panel_limits_for_double(self.panel_right, local2.height())
        self.panel_left.setGeometry(local1)
        self.panel_right.setGeometry(local2)
        double_geom_debug(
            "applied got p1=%s p2=%s (mismatch vs req = silent clamp)",
            self._dbg_rect(self.panel_left.geometry()),
            self._dbg_rect(self.panel_right.geometry()),
        )
        for panel in (self.panel_left, self.panel_right):
            try:
                panel._controller.rebind()
            except (AttributeError, RuntimeError):
                pass

        if hasattr(self.panel_left, "_check_scrollbar"):
            self.panel_left._check_scrollbar()
        if hasattr(self.panel_right, "_check_scrollbar"):
            self.panel_right._check_scrollbar()

    @staticmethod
    def _relax_panel_limits_for_double(panel, height: int) -> None:
        """Grow-only guard: let the DOUBLE shared height actually apply."""
        height = max(1, int(height))
        try:
            if panel.maximumHeight() < height:
                panel.setMaximumHeight(height)
            if panel.minimumHeight() > height:
                panel.setMinimumHeight(height)
            scroll_area = getattr(panel, "scroll_area", None)
            if scroll_area is not None:
                if scroll_area.maximumHeight() < height:
                    scroll_area.setMaximumHeight(height)
                if scroll_area.minimumHeight() > height:
                    scroll_area.setMinimumHeight(height)
        except RuntimeError:
            return
        try:
            panel._container_height = height
        except AttributeError:
            pass

    def _position_panels_for_single(self):
        inner = self.container_widget.rect()
        self.panel_left.setGeometry(inner)
        self.panel_right.setGeometry(inner)

        active_panel = (
            self.panel_left if self.panel_left.isVisible() else self.panel_right
        )
        if active_panel and hasattr(active_panel, "scroll_area"):
            active_panel.scroll_area.setWidgetResizable(True)

    def _calc_panel_total_size(self, list_num: int) -> QSize:
        panel = self.panel_left if list_num == 1 else self.panel_right
        related_button = self.anchor_for_list(list_num)
        try:
            panel.adjustSize()
        except Exception:
            pass
        # Match the anchor button width exactly so the panel never extends past
        # its anchor. Fall back to a 200 px floor only if the button has not
        # been sized yet.
        width = related_button.width() if related_button is not None and related_button.width() > 0 else 200
        double_geom_debug(
            "panel_size list=%s w=%s (anchor=%s) cont_h=%s n_items=%s",
            list_num,
            width,
            type(related_button).__name__ if related_button is not None else None,
            panel._container_height,
            len(panel._items),
        )
        return QSize(width, panel._container_height)

    def _calculate_ideal_geometry(
        self, anchor_widget: QWidget, panel_size: QSize, content_only=False
    ) -> QRect:
        anchor_rect = surface_anchor_rect(self, anchor_widget, self.overlay_layer)
        content_rect = QRect(
            anchor_rect.x(),
            anchor_rect.y() + anchor_rect.height() + self.SINGLE_PANEL_GAP_Y,
            panel_size.width(),
            panel_size.height(),
        )
        if content_only:
            return content_rect
        return self._outer_from_content_rect(content_rect)

    def _calculate_ideal_content_geometry(
        self, anchor_widget: QWidget, panel_size: QSize, extra_y: int = 0
    ) -> QRect:
        rect = self._calculate_ideal_geometry(
            anchor_widget, panel_size, content_only=True
        )
        if extra_y:
            rect.translate(0, extra_y)
        return rect

    def _update_geometry_in_double_mode_internal(self):
        button1 = self._anchor_left
        button2 = self._anchor_right
        if button1 is None or button2 is None:
            double_geom_debug(
                "SKIP double geometry: anchors missing l=%s r=%s "
                "(panels keep stale geometry!)",
                button1 is not None,
                button2 is not None,
            )
            return
        self._sync_double_mode_button_state(button1, button2)
        panel1_local, panel2_local, final_unified_geom = (
            self._compute_double_mode_geometry(button1, button2)
        )
        self.setGeometry(final_unified_geom)
        self._apply_container_geometry()
        self._apply_panel_geometries(panel1_local, panel2_local)
        self._ensure_double_mode_scroll_behavior()
        double_geom_debug(
            "double applied outer=%s",
            self._dbg_rect(self.geometry()),
        )

    def _sync_double_mode_button_state(self, button1, button2):
        # Body lives in double_geometry.py (pure function over the picker
        # owner); this delegator keeps the Plan 1 method name on the mixin.
        return sync_double_mode_button_state(self, button1, button2)

    def _resolve_double_mode_top(
        self, button1, button2, geom1_content: QRect, geom2_content: QRect
    ) -> int:
        """Shared content height for DOUBLE mode, honoring the resolved top.

        Body lives in double_geometry.py; see resolve_double_mode_top.
        """
        return resolve_double_mode_top(
            self, button1, button2, geom1_content, geom2_content
        )

    def _compute_double_mode_geometry(self, button1, button2):
        # Body lives in double_geometry.py; this delegator keeps the Plan 1
        # method name on the mixin.
        return compute_double_mode_geometry(self, button1, button2)

    def _ensure_double_mode_scroll_behavior(self):
        return ensure_double_mode_scroll_behavior(self)

    def updateGeometryInDoubleMode(self):
        if self.mode != FlyoutMode.DOUBLE:
            return
        self.refreshGeometry()