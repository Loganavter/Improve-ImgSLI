import logging
import time
import traceback
from enum import Enum
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget

from PyQt6.QtWidgets import QGraphicsEffect

class _RoundedClipEffect(QGraphicsEffect):
    def __init__(self, radius=8, parent=None):
        super().__init__(parent)
        self._radius = radius

    def draw(self, painter: QPainter):
        src = self.sourceBoundingRect()
        if src.isEmpty():
            return
        clip = QPainterPath()
        clip.addRoundedRect(src, self._radius, self._radius)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        self.drawSource(painter)
        painter.restore()

from core.constants import AppConstants
from events.drag_drop_handler import DragAndDropService
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from shared_toolkit.ui.widgets.helpers import draw_rounded_shadow
from shared_toolkit.ui.widgets.composite.unified_flyout.panel import (
    _ListOwnerProxy,
    _Panel,
)

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext

logger = logging.getLogger("ImproveImgSLI")

class FlyoutMode(Enum):
    HIDDEN = 0
    SINGLE_LEFT = 1
    SINGLE_RIGHT = 2
    DOUBLE = 3
    SINGLE_SIMPLE = 4

class UnifiedFlyout(QWidget):
    item_chosen = pyqtSignal(int, int)
    simple_item_chosen = pyqtSignal(int)
    closing_animation_finished = pyqtSignal()

    SHADOW_RADIUS = 10
    MARGIN = 0
    SINGLE_APPEAR_EXTRA_Y = 6
    DOUBLE_CONTENT_EXTRA_Y = 6

    _move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS
    _move_easing = QEasingCurve.Type.OutQuad
    _drop_offset_px = 80

    def __init__(self, store, main_controller, main_window):
        super().__init__(main_window)
        self.store = store
        self.main_controller = main_controller
        self.main_window = main_window
        self.overlay_layer = get_overlay_layer(main_window)
        if self.overlay_layer is not None:
            self.overlay_layer.attach(self)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._init_container_and_panels()
        self._init_clipping()
        self._init_owner_proxies()
        self._init_drag_drop()
        self._init_theme()
        self.hide()

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

    def _apply_style(self):
        if self.mode == FlyoutMode.DOUBLE:
            self._container_clip.setEnabled(False)
            self.container_widget.setProperty("surfaceRole", "transparent")
            self.panel_left.setProperty("surfaceRole", "panel")
            self.panel_right.setProperty("surfaceRole", "panel")
            self._panel_left_clip.setEnabled(True)
            self._panel_right_clip.setEnabled(True)
        else:
            self._panel_left_clip.setEnabled(False)
            self._panel_right_clip.setEnabled(False)
            self._container_clip.setEnabled(True)
            self.container_widget.setProperty("surfaceRole", "container")
            self.panel_left.setProperty("surfaceRole", "transparent")
            self.panel_right.setProperty("surfaceRole", "transparent")

        for widget in (self.container_widget, self.panel_left, self.panel_right):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _apply_container_geometry(self):
        inner_rect = self.rect().adjusted(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
        )
        if self.container_widget.geometry() != inner_rect:
            self.container_widget.setGeometry(inner_rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_container_geometry()

        if self.mode != FlyoutMode.DOUBLE:
            self._position_panels_for_single()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        steps = self.SHADOW_RADIUS

        if self.mode == FlyoutMode.DOUBLE:
            offset = self.container_widget.geometry().topLeft()
            for panel in (self.panel_left, self.panel_right):
                if panel.isVisible():
                    pr = QRectF(panel.geometry()).translated(offset.x(), offset.y())
                    self._draw_shadow(painter, pr, steps)
        else:
            cr = QRectF(self.container_widget.geometry())
            self._draw_shadow(painter, cr, steps)
        painter.end()

    def _draw_shadow(self, painter, rect, steps):
        draw_rounded_shadow(painter, rect, steps=steps, radius=8)

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
            reason = []
            if self.mode == FlyoutMode.DOUBLE:
                reason.append("уже DOUBLE")
            if not self.isVisible():
                reason.append("не видим")
            if self._is_simple_mode:
                reason.append("simple режим")
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
        button_width = related_button.width()

        panel_container_height = panel._container_height

        if self.mode == FlyoutMode.DOUBLE:

            w = max(button_width, 200)
        else:

            w = max(button_width, 200)

        h = panel_container_height

        return QSize(w, h)

    def _calculate_ideal_geometry(
        self, anchor_widget: QWidget, panel_size: QSize, content_only=False
    ) -> QRect:
        current_panel_h = panel_size.height()

        button_pos_relative = anchor_widget.mapTo(self.main_window, QPoint(0, 0))

        content_width = panel_size.width()
        content_height = current_panel_h

        content_x = button_pos_relative.x()
        content_y = button_pos_relative.y() + anchor_widget.height() - 4

        content_rect = QRect(content_x, content_y, content_width, content_height)

        if content_only:
            return content_rect

        result = content_rect.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        return result

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
        count1 = len(list1)
        count2 = len(list2)
        idx1 = self.store.document.current_index1
        idx2 = self.store.document.current_index2
        items1 = [item.display_name for item in list1] if list1 else []
        items2 = [item.display_name for item in list2] if list2 else []
        text1 = items1[idx1] if 0 <= idx1 < count1 and items1 else ""
        text2 = items2[idx2] if 0 <= idx2 < count2 and items2 else ""
        button1.updateState(count1, idx1, text=text1, items=items1)
        button2.updateState(count2, idx2, text=text2, items=items2)

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

    def _do_refresh_geometry(self):
        self.refreshGeometry(immediate=True)

    def refreshGeometry(self, immediate=False):
        if not immediate:
            self._schedule_geometry_refresh()
            return

        if not self._begin_immediate_refresh():
            return

        if self._should_abort_refresh():
            self._is_refreshing = False
            return

        list1 = self.store.document.image_list1
        list2 = self.store.document.image_list2

        if not list1 and not list2:
            self._finish_refresh_with_close()
            return

        if self._handle_mode_transitions_for_lists(list1, list2):
            self._is_refreshing = False
            return

        self.panel_left.recalculate_and_set_height()
        self.panel_right.recalculate_and_set_height()
        self._apply_refreshed_geometry()
        self._apply_style()
        self.raise_()
        self._is_refreshing = False

    def _schedule_geometry_refresh(self):
        if self._is_refreshing:
            if not self._refresh_timer.isActive():
                self._refresh_timer.start(50)
            return
        if self._refresh_timer.isActive():
            return
        self._refresh_timer.start(50)

    def _begin_immediate_refresh(self) -> bool:
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        if self._is_refreshing:
            return False
        self._is_refreshing = True
        self._apply_style()
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        return True

    def _should_abort_refresh(self) -> bool:
        return not self.isVisible() or self._is_closing

    def _finish_refresh_with_close(self):
        self._is_refreshing = False
        self.start_closing_animation()

    def _handle_mode_transitions_for_lists(self, list1, list2) -> bool:
        if self.mode == FlyoutMode.DOUBLE:
            if not list1:
                self._switch_double_to_single(2)
            elif not list2:
                self._switch_double_to_single(1)
            return False
        if self.mode == FlyoutMode.SINGLE_LEFT and not list1:
            self.start_closing_animation()
            return True
        if self.mode == FlyoutMode.SINGLE_RIGHT and not list2:
            self.start_closing_animation()
            return True
        return False

    def _switch_double_to_single(self, list_num: int):
        self.mode = FlyoutMode.SINGLE_RIGHT if list_num == 2 else FlyoutMode.SINGLE_LEFT
        self.source_list_num = list_num
        if list_num == 2:
            self.panel_left.hide()
            self.panel_right.show()
            if self.main_window:
                self.main_window.ui.combo_image1.setFlyoutOpen(False)
                self.main_window.ui.combo_image2.setFlyoutOpen(True)
        else:
            self.panel_right.hide()
            self.panel_left.show()
            if self.main_window:
                self.main_window.ui.combo_image2.setFlyoutOpen(False)
                self.main_window.ui.combo_image1.setFlyoutOpen(True)

    def _apply_refreshed_geometry(self):
        if self.mode == FlyoutMode.DOUBLE:
            self.panel_left.show()
            self.panel_right.show()
            self._update_geometry_in_double_mode_internal()
            return
        self._apply_single_mode_refresh_geometry()

    def _apply_single_mode_refresh_geometry(self):
        is_left = self.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_SIMPLE)
        active_panel = self.panel_left if is_left else self.panel_right
        anchor = (
            self.main_window.ui.combo_image1
            if is_left
            else self.main_window.ui.combo_image2
        )
        active_list_num = 1 if is_left else 2
        active_panel.show()
        (self.panel_right if is_left else self.panel_left).hide()
        if hasattr(anchor, "setFlyoutOpen"):
            anchor.setFlyoutOpen(True)
        panel_size = self._calc_panel_total_size(active_list_num)
        content_rect = self._calculate_ideal_content_geometry(
            anchor, panel_size, extra_y=self.SINGLE_APPEAR_EXTRA_Y
        )
        container_rect = content_rect.adjusted(
            -self.SHADOW_RADIUS,
            -self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        self.setGeometry(container_rect)
        self._apply_container_geometry()
        self._position_panels_for_single()

    def populate(self, list_num: int, items: list, list_type="image", current_index=-1):
        panel = (
            self.panel_left
            if (list_num == 1 or list_type == "simple")
            else self.panel_right
        )

        if list_type == "simple":
            owner = self._owner_proxy_simple
        else:
            owner = self._owner_proxy_left if list_num == 1 else self._owner_proxy_right

        panel.clear_and_rebuild(
            items, owner, self.item_height, self.item_font, list_type, current_index
        )

        if self.mode == FlyoutMode.DOUBLE:

            self.refreshGeometry()

    def sync_from_store(self):
        if not self.isVisible():
            return
        if self._is_simple_mode:
            return

        self.panel_left.sync_with_list(
            self.store.document.image_list1,
            self._owner_proxy_left,
            self.item_height,
            self.item_font,
            "image",
            self.store.document.current_index1,
        )
        self.panel_right.sync_with_list(
            self.store.document.image_list2,
            self._owner_proxy_right,
            self.item_height,
            self.item_font,
            "image",
            self.store.document.current_index2,
        )
        QTimer.singleShot(0, lambda: self.refreshGeometry(immediate=True))

    def update_rating_for_item(self, image_number: int, index: int):
        if not self.isVisible():
            return

        panel = self.panel_left if image_number == 1 else self.panel_right
        if panel and panel.isVisible():
            panel.update_rating_for_item(index)

    def _on_item_selected(self, list_num: int, index: int):
        if self._is_simple_mode:
            self.simple_item_chosen.emit(index)
        else:
            if self.main_controller and self.main_controller.session_ctrl:
                self.main_controller.session_ctrl.on_combobox_changed(list_num, index)
            self.item_chosen.emit(list_num, index)

        self.start_closing_animation()

    def _on_item_right_clicked(self, list_num, index):
        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.remove_specific_image_from_list(
                list_num, index
            )

    def _get_current_index(self, image_number: int) -> int:
        if image_number == 1:
            return self.store.document.current_index1
        if image_number == 2:
            return self.store.document.current_index2
        return -1

    def _get_item_rating(self, image_number: int, index: int) -> int:
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )
        if 0 <= index < len(target_list):
            return getattr(target_list[index], "rating", 0)
        return 0

    def _create_rating_gesture(
        self, image_number: int, item_index: int, starting_score: int
    ):
        if self.main_controller is None:
            return None
        from shared_toolkit.ui.gesture_resolver import RatingGestureTransaction

        return RatingGestureTransaction(
            main_controller=self.main_controller,
            image_number=image_number,
            item_index=item_index,
            starting_score=starting_score,
        )

    def _increment_rating(self, image_number: int, index: int) -> None:
        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.increment_rating(image_number, index)

    def _decrement_rating(self, image_number: int, index: int) -> None:
        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.decrement_rating(image_number, index)

    def _reorder_item(self, image_number: int, source_index: int, dest_index: int) -> None:
        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.reorder_item_in_list(
                image_number=image_number,
                source_index=source_index,
                dest_index=dest_index,
            )

    def _move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        if self.main_controller and self.main_controller.session_ctrl:
            self.main_controller.session_ctrl.move_item_between_lists(
                source_list_num=source_list_num,
                source_index=source_index,
                dest_list_num=dest_list_num,
                dest_index=dest_index,
            )

    def start_closing_animation(self):
        if not self.isVisible() or self._is_closing:
            return
        self.hide()

    def _on_animation_finished(self):
        if self._anim:
            self._anim.deleteLater()
            self._anim = None

    def hideEvent(self, event):
        closing_mode = self.mode
        if self._anim:
            self._anim.stop()
        PathTooltip.get_instance().hide_tooltip()

        self.last_close_timestamp = time.monotonic()
        self.last_close_mode = closing_mode

        if not self._is_closing:
            self._is_closing = True
            try:
                self.mode = FlyoutMode.HIDDEN
                self.closing_animation_finished.emit()
            finally:
                self._is_closing = False

        super().hideEvent(event)

    def can_accept_drop(self, payload: dict) -> bool:
        return self.isVisible()

    def _panel_under_global_pos(self, global_pos: QPointF):
        local_pos = self.container_widget.mapFromGlobal(global_pos.toPoint())

        if self.mode == FlyoutMode.DOUBLE:
            if self.panel_left.geometry().contains(local_pos):
                return self.panel_left
            if self.panel_right.geometry().contains(local_pos):
                return self.panel_right
            return None
        else:
            result = (
                self.panel_left
                if self.panel_left.isVisible()
                else (self.panel_right if self.panel_right.isVisible() else None)
            )
            return result

    def update_drop_indicator(self, global_pos: QPointF):
        panel = self._panel_under_global_pos(global_pos)
        if panel is None:
            self.clear_drop_indicator()
            return

        other = self.panel_right if panel is self.panel_left else self.panel_left
        try:
            panel.update_drop_indicator(global_pos)
            other.clear_drop_indicator()
        except Exception as e:
            logger.exception(f"[UnifiedFlyout] exception in update_drop_indicator: {e}")

    def clear_drop_indicator(self):
        self.panel_left.clear_drop_indicator()
        self.panel_right.clear_drop_indicator()

    def handle_drop(self, payload: dict, global_pos: QPointF):
        panel = self._panel_under_global_pos(global_pos)
        if panel:
            panel.handle_drop(payload, global_pos)
