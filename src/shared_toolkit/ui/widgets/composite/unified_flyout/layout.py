from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize
from PyQt6.QtWidgets import QApplication, QWidget

from shared_toolkit.ui.widgets.composite.unified_flyout.common import FlyoutMode

class _UnifiedFlyoutLayoutMixin:
    _move_easing = QEasingCurve.Type.OutQuad
    _drop_offset_px = 80

    def showAsSingle(
        self,
        list_num: int,
        anchor_widget: QWidget,
        list_type="image",
        simple_items=None,
        simple_current_index=-1,
    ):
        if self._anim:
            self._anim.stop()

        self.source_list_num = list_num
        self._is_simple_mode = list_type == "simple"
        self._set_single_mode(list_num)
        self._apply_style()
        self.item_height = getattr(anchor_widget, "getItemHeight", lambda: 34)()
        self.item_font = getattr(
            anchor_widget, "getItemFont", lambda: QApplication.font()
        )()
        active_list_num = self._populate_for_single_mode(
            list_num, simple_items, simple_current_index
        )
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
        self.populate(1, self.store.document.image_list1)
        self.populate(2, self.store.document.image_list2)
        self.panel_left.setVisible(list_num == 1)
        self.panel_right.setVisible(list_num == 2)
        return list_num

    def _build_single_mode_geometry(
        self, anchor_widget: QWidget, active_list_num: int
    ) -> tuple[QRect, QPoint, QPoint]:
        panel_size = self._calc_panel_total_size(active_list_num)
        content_rect = self._calculate_ideal_content_geometry(
            anchor_widget, panel_size, extra_y=self.SINGLE_APPEAR_EXTRA_Y
        )
        ideal_geom = content_rect.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        end_pos = ideal_geom.topLeft()
        start_pos = QPoint(end_pos.x(), end_pos.y() - self._drop_offset_px)
        return ideal_geom, start_pos, end_pos

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
        related_button = (
            self.main_window.ui.combo_image1
            if list_num == 1
            else self.main_window.ui.combo_image2
        )
        return QSize(max(related_button.width(), 200), panel._container_height)

    def _calculate_ideal_geometry(
        self, anchor_widget: QWidget, panel_size: QSize, content_only=False
    ) -> QRect:
        button_pos_relative = anchor_widget.mapTo(self.main_window, QPoint(0, 0))
        content_rect = QRect(
            button_pos_relative.x(),
            button_pos_relative.y() + anchor_widget.height() - 4,
            panel_size.width(),
            panel_size.height(),
        )
        if content_only:
            return content_rect
        return content_rect.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )

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
        button1 = self.main_window.ui.combo_image1
        button2 = self.main_window.ui.combo_image2
        self._sync_double_mode_button_state(button1, button2)
        panel1_local, panel2_local, final_unified_geom = (
            self._compute_double_mode_geometry(button1, button2)
        )
        self.setGeometry(final_unified_geom)
        self._apply_container_geometry()
        self._apply_panel_geometries(panel1_local, panel2_local)
        self._ensure_double_mode_scroll_behavior()

    def _sync_double_mode_button_state(self, button1, button2):
        list1 = self.store.document.image_list1
        list2 = self.store.document.image_list2
        idx1 = self.store.document.current_index1
        idx2 = self.store.document.current_index2
        items1 = [item.display_name for item in list1] if list1 else []
        items2 = [item.display_name for item in list2] if list2 else []
        text1 = items1[idx1] if 0 <= idx1 < len(items1) else ""
        text2 = items2[idx2] if 0 <= idx2 < len(items2) else ""
        button1.updateState(len(list1), idx1, text=text1, items=items1)
        button2.updateState(len(list2), idx2, text=text2, items=items2)

    def _compute_double_mode_geometry(self, button1, button2):
        left_size = self._calc_panel_total_size(1)
        right_size = self._calc_panel_total_size(2)
        geom1_content = self._calculate_ideal_geometry(
            button1, left_size, content_only=True
        ).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
        geom2_content = self._calculate_ideal_geometry(
            button2, right_size, content_only=True
        ).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
        original_h1 = geom1_content.height()
        original_h2 = geom2_content.height()
        unified_content = geom1_content.united(geom2_content)
        final_unified_geom = unified_content.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        clamped_content = final_unified_geom.adjusted(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
        )
        delta_y = clamped_content.y() - unified_content.y()
        unified_h = clamped_content.height()
        geom1_content = QRect(
            geom1_content.x(),
            geom1_content.y() + delta_y,
            geom1_content.width(),
            original_h1,
        )
        geom2_content = QRect(
            geom2_content.x(),
            geom2_content.y() + delta_y,
            geom2_content.width(),
            original_h2,
        )
        unified_content = QRect(
            clamped_content.x(), clamped_content.y(), clamped_content.width(), unified_h
        )
        panel1_local = QRect(
            geom1_content.x() - unified_content.x(),
            geom1_content.y() - unified_content.y(),
            geom1_content.width(),
            geom1_content.height(),
        )
        panel2_local = QRect(
            geom2_content.x() - unified_content.x(),
            geom2_content.y() - unified_content.y(),
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
