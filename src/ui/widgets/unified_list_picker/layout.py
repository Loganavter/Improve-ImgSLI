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
    current_index_for_list,
    items_for_list,
)

class _UnifiedFlyoutLayoutMixin(_UnifiedFlyoutBase):
    mode: FlyoutMode
    _move_easing = QEasingCurve.Type.OutQuad

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
        if (
            self.mode == FlyoutMode.DOUBLE
            or not self.isVisible()
            or self._is_simple_mode
        ):
            return

        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        self.mode = FlyoutMode.DOUBLE
        self.panel_left.show()
        self.panel_right.show()
        self._sync_anchor_open_state(None)
        self._apply_style()
        self._update_geometry_in_double_mode_internal()
        self.raise_()

    def _apply_panel_geometries(self, local1: QRect, local2: QRect):
        self.panel_left.setGeometry(local1)
        self.panel_right.setGeometry(local2)

        if hasattr(self.panel_left, "_check_scrollbar"):
            self.panel_left._check_scrollbar()
        if hasattr(self.panel_right, "_check_scrollbar"):
            self.panel_right._check_scrollbar()

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
            return
        self._sync_double_mode_button_state(button1, button2)
        panel1_local, panel2_local, final_unified_geom = (
            self._compute_double_mode_geometry(button1, button2)
        )
        self.setGeometry(final_unified_geom)
        self._apply_container_geometry()
        self._apply_panel_geometries(panel1_local, panel2_local)
        self._ensure_double_mode_scroll_behavior()

    def _sync_double_mode_button_state(self, button1, button2):
        list1 = items_for_list(self._document(), 1)
        list2 = items_for_list(self._document(), 2)
        idx1 = current_index_for_list(self._document(), 1)
        idx2 = current_index_for_list(self._document(), 2)
        items1 = [item.display_name for item in list1] if list1 else []
        items2 = [item.display_name for item in list2] if list2 else []
        text1 = items1[idx1] if 0 <= idx1 < len(items1) else ""
        text2 = items2[idx2] if 0 <= idx2 < len(items2) else ""
        if hasattr(button1, "updateState"):
            button1.updateState(len(list1), idx1, text=text1, items=items1)
        if hasattr(button2, "updateState"):
            button2.updateState(len(list2), idx2, text=text2, items=items2)

    def _compute_double_mode_geometry(self, button1, button2):
        left_size = self._calc_panel_total_size(1)
        right_size = self._calc_panel_total_size(2)
        geom1_content = self._calculate_ideal_geometry(
            button1, left_size, content_only=True
        )
        geom2_content = self._calculate_ideal_geometry(
            button2, right_size, content_only=True
        )
        source_anchor = button1 if self.source_list_num == 1 else button2
        source_panel = self.panel_left if self.source_list_num == 1 else self.panel_right
        source_rect = geom1_content if self.source_list_num == 1 else geom2_content
        _source_y, shared_height = self._resolve_content_y_and_height(
            source_anchor,
            source_rect.y(),
            max(geom1_content.height(), geom2_content.height()),
            source_panel,
        )
        if shared_height < max(
            self.panel_left._container_height,
            self.panel_right._container_height,
        ):
            self.panel_left.recalculate_and_set_height(max_height=shared_height)
            self.panel_right.recalculate_and_set_height(max_height=shared_height)
            left_size = self._calc_panel_total_size(1)
            right_size = self._calc_panel_total_size(2)
            geom1_content = self._calculate_ideal_geometry(
                button1, left_size, content_only=True
            )
            geom2_content = self._calculate_ideal_geometry(
                button2, right_size, content_only=True
            )
            source_panel = self.panel_left if self.source_list_num == 1 else self.panel_right
            source_rect = geom1_content if self.source_list_num == 1 else geom2_content
            _source_y, shared_height = self._resolve_content_y_and_height(
                source_anchor,
                source_rect.y(),
                max(geom1_content.height(), geom2_content.height()),
                source_panel,
            )
        geom1_content.setHeight(shared_height)
        geom2_content.setHeight(shared_height)

        unified_content = geom1_content.united(geom2_content)
        final_unified_geom = self._clamp_outer_rect(
            self._outer_from_content_rect(unified_content),
            allow_resize=False,
        )
        clamped_content = final_unified_geom.adjusted(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
        )
        delta = clamped_content.topLeft() - unified_content.topLeft()
        max_panel_height = max(1, clamped_content.height())
        if max_panel_height < max(
            self.panel_left._container_height,
            self.panel_right._container_height,
        ):
            self.panel_left.recalculate_and_set_height(max_height=max_panel_height)
            self.panel_right.recalculate_and_set_height(max_height=max_panel_height)
            geom1_content.setHeight(self.panel_left._container_height)
            geom2_content.setHeight(self.panel_right._container_height)
            unified_content = geom1_content.united(geom2_content)
            final_unified_geom = self._clamp_outer_rect(
                self._outer_from_content_rect(unified_content),
                allow_resize=True,
            )
            clamped_content = final_unified_geom.adjusted(
                self.SHADOW_RADIUS,
                self.SHADOW_RADIUS,
                -self.SHADOW_RADIUS,
                -self.SHADOW_RADIUS,
            )
            delta = clamped_content.topLeft() - unified_content.topLeft()
        geom1_content = QRect(
            geom1_content.x() + delta.x(),
            geom1_content.y() + delta.y(),
            geom1_content.width(),
            min(geom1_content.height(), max_panel_height),
        )
        geom2_content = QRect(
            geom2_content.x() + delta.x(),
            geom2_content.y() + delta.y(),
            geom2_content.width(),
            min(geom2_content.height(), max_panel_height),
        )
        panel1_local = QRect(
            geom1_content.x() - clamped_content.x(),
            geom1_content.y() - clamped_content.y(),
            geom1_content.width(),
            geom1_content.height(),
        )
        panel2_local = QRect(
            geom2_content.x() - clamped_content.x(),
            geom2_content.y() - clamped_content.y(),
            geom2_content.width(),
            geom2_content.height(),
        )
        return panel1_local, panel2_local, final_unified_geom

    def _ensure_double_mode_scroll_behavior(self):
        for panel in (self.panel_left, self.panel_right):
            if hasattr(panel, "scroll_area"):
                panel.scroll_area.setWidgetResizable(True)

    def updateGeometryInDoubleMode(self):
        if self.mode != FlyoutMode.DOUBLE:
            return
        self.refreshGeometry()