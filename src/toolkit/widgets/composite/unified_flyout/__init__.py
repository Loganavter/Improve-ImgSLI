from enum import Enum
import logging
import time
import traceback
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QTimer, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

from core.constants import AppConstants
from events.drag_drop_handler import DragAndDropService
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.tooltips import PathTooltip
from toolkit.widgets.composite.unified_flyout.panel import _ListOwnerProxy, _Panel

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

        self.mode = FlyoutMode.HIDDEN
        self.source_list_num = 1
        self._is_closing = False
        self.item_height = 36
        self.item_font = None
        self.last_close_timestamp = 0.0
        self._anim = None
        self._is_simple_mode = False
        self._is_refreshing = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_geometry)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("FlyoutWidget")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(self.SHADOW_RADIUS)
        shadow.setOffset(1, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container_widget.setGraphicsEffect(shadow)

        self.panel_left = _Panel(store, main_controller, main_window, 1, self.item_height, self.item_font, self.container_widget)
        self.panel_right = _Panel(store, main_controller, main_window, 2, self.item_height, self.item_font, self.container_widget)

        self._owner_proxy_left = _ListOwnerProxy(1)
        self._owner_proxy_right = _ListOwnerProxy(2)
        self._owner_proxy_simple = _ListOwnerProxy(0)

        DragAndDropService.get_instance().register_drop_target(self)
        self.destroyed.connect(self._on_destroyed)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()

        self.hide()

    def _on_destroyed(self):
        try:
            DragAndDropService.get_instance().unregister_drop_target(self)
        except Exception:
            pass

    def _apply_style(self):
        bg = None
        border = None
        try:
            bg = self.theme_manager.get_color("flyout.background")
            border = self.theme_manager.get_color("flyout.border")
        except Exception:
            pass

        bg_str = bg.name(QColor.NameFormat.HexArgb) if bg else ""
        border_str = border.name(QColor.NameFormat.HexArgb) if border else ""

        if self.mode == FlyoutMode.DOUBLE:
            self.container_widget.setStyleSheet("background: transparent; border: none;")
            panel_style = ""
            if bg_str or border_str:
                panel_style = (
                    f"background:{bg_str};"
                    f"border: 1px solid {border_str or 'transparent'};"
                    "border-radius: 8px;"
                )
            self.panel_left.setStyleSheet(panel_style)
            self.panel_right.setStyleSheet(panel_style)
        else:

            self.container_widget.setStyleSheet("")
            self.panel_left.setStyleSheet("background: transparent; border: none;")
            self.panel_right.setStyleSheet("background: transparent; border: none;")

    def _apply_container_geometry(self):
        inner_rect = self.rect().adjusted(self.SHADOW_RADIUS, self.SHADOW_RADIUS, -self.SHADOW_RADIUS, -self.SHADOW_RADIUS)
        if self.container_widget.geometry() != inner_rect:
            self.container_widget.setGeometry(inner_rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_container_geometry()

        if self.mode != FlyoutMode.DOUBLE:
            self._position_panels_for_single()

    def showAsSingle(self, list_num: int, anchor_widget: QWidget, list_type="image", simple_items=None, simple_current_index=-1):
        if self._anim:
            self._anim.stop()

        self.source_list_num = list_num
        self._is_simple_mode = (list_type == "simple")

        if self._is_simple_mode:
            self.mode = FlyoutMode.SINGLE_SIMPLE
        else:
            self.mode = FlyoutMode.SINGLE_LEFT if list_num == 1 else FlyoutMode.SINGLE_RIGHT

        self._apply_style()

        self.item_height = getattr(anchor_widget, 'getItemHeight', lambda: 34)()
        self.item_font = getattr(anchor_widget, 'getItemFont', lambda: QApplication.font())()

        if self._is_simple_mode:
            self.populate(0, simple_items, list_type="simple", current_index=simple_current_index)
            self.panel_left.show()
            self.panel_right.hide()
            active_list_num = 1
        else:
            self.populate(1, self.store.document.image_list1)
            self.populate(2, self.store.document.image_list2)
            self.panel_left.setVisible(list_num == 1)
            self.panel_right.setVisible(list_num == 2)
            active_list_num = list_num

        panel_size = self._calc_panel_total_size(active_list_num)

        content_rect = self._calculate_ideal_content_geometry(
            anchor_widget, panel_size, extra_y=self.SINGLE_APPEAR_EXTRA_Y
        )
        ideal_geom = content_rect.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)

        end_pos = ideal_geom.topLeft()
        start_pos = QPoint(end_pos.x(), end_pos.y() - self._drop_offset_px)

        self.resize(ideal_geom.size())
        self.move(start_pos)
        self._apply_container_geometry()
        self._position_panels_for_single()
        self.show()
        self.raise_()

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(self._move_duration_ms)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(end_pos)
        self._anim.setEasingCurve(self._move_easing)
        self._anim.finished.connect(self._on_animation_finished)
        self._anim.start()

    def switchToDoubleMode(self):

        if self.mode == FlyoutMode.DOUBLE or not self.isVisible() or self._is_simple_mode:
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

    def _apply_panel_geometries(self, local1: QRect, local2: QRect):
        self.panel_left.setGeometry(local1)
        self.panel_right.setGeometry(local2)

        if hasattr(self.panel_left, '_check_scrollbar'):
            self.panel_left._check_scrollbar()
        if hasattr(self.panel_right, '_check_scrollbar'):
            self.panel_right._check_scrollbar()

    def _position_panels_for_single(self):
        inner = self.container_widget.rect()
        self.panel_left.setGeometry(inner)
        self.panel_right.setGeometry(inner)

        active_panel = self.panel_left if self.panel_left.isVisible() else self.panel_right
        if active_panel and hasattr(active_panel, 'scroll_area'):
             active_panel.scroll_area.setWidgetResizable(True)

    def _calc_panel_total_size(self, list_num: int) -> QSize:
        panel = self.panel_left if list_num == 1 else self.panel_right

        related_button = self.main_window.ui.combo_image1 if list_num == 1 else self.main_window.ui.combo_image2
        button_width = related_button.width()

        panel_container_height = panel._container_height

        if self.mode == FlyoutMode.DOUBLE:

            w = max(button_width, 200)
        else:

            w = max(button_width, 200)

        h = panel_container_height

        logger.debug(f"[UnifiedFlyout] _calc_panel_total_size(list_num={list_num}, mode={self.mode}): button_width={button_width}, final=({w}, {h})")

        return QSize(w, h)

    def _calculate_ideal_geometry(self, anchor_widget: QWidget, panel_size: QSize, content_only=False) -> QRect:
        current_panel_h = panel_size.height()

        button_pos_relative = anchor_widget.mapTo(self.main_window, QPoint(0, 0))

        content_width = panel_size.width()
        content_height = current_panel_h

        content_x = button_pos_relative.x()
        content_y = button_pos_relative.y() + anchor_widget.height() - 4

        content_rect = QRect(content_x, content_y, content_width, content_height)

        logger.debug(f"[UnifiedFlyout] _calculate_ideal_geometry: anchor={anchor_widget.objectName()}, panel_size={panel_size}, content_rect={content_rect}")

        if content_only:
            return content_rect

        result = content_rect.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)
        return result

    def _calculate_ideal_content_geometry(self, anchor_widget: QWidget, panel_size: QSize, extra_y: int = 0) -> QRect:
        rect = self._calculate_ideal_geometry(anchor_widget, panel_size, content_only=True)
        if extra_y:
            rect.translate(0, extra_y)
        return rect

    def _update_geometry_in_double_mode_internal(self):
        button1 = self.main_window.ui.combo_image1
        button2 = self.main_window.ui.combo_image2

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

        left_size = self._calc_panel_total_size(1)
        right_size = self._calc_panel_total_size(2)

        geom1_content = self._calculate_ideal_geometry(button1, left_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
        geom2_content = self._calculate_ideal_geometry(button2, right_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)

        original_h1 = geom1_content.height()
        original_h2 = geom2_content.height()

        unified_content = geom1_content.united(geom2_content)

        ideal_outer = unified_content.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)
        final_unified_geom = ideal_outer
        clamped_content = final_unified_geom.adjusted(self.SHADOW_RADIUS, self.SHADOW_RADIUS, -self.SHADOW_RADIUS, -self.SHADOW_RADIUS)

        delta_y = clamped_content.y() - unified_content.y()

        unified_h = clamped_content.height()

        geom1_content = QRect(geom1_content.x(), geom1_content.y() + delta_y, geom1_content.width(), original_h1)
        geom2_content = QRect(geom2_content.x(), geom2_content.y() + delta_y, geom2_content.width(), original_h2)

        unified_content = QRect(clamped_content.x(), clamped_content.y(), clamped_content.width(), unified_h)

        panel1_local = QRect(geom1_content.x() - unified_content.x(),
                             geom1_content.y() - unified_content.y(),
                             geom1_content.width(), geom1_content.height())

        panel2_local = QRect(geom2_content.x() - unified_content.x(),
                             geom2_content.y() - unified_content.y(),
                             geom2_content.width(), geom2_content.height())

        self.setGeometry(final_unified_geom)
        self._apply_container_geometry()
        self._apply_panel_geometries(panel1_local, panel2_local)

        for panel in [self.panel_left, self.panel_right]:
            if hasattr(panel, 'scroll_area'):
                 panel.scroll_area.setWidgetResizable(True)

    def updateGeometryInDoubleMode(self):
        if self.mode != FlyoutMode.DOUBLE:
            return

        self.refreshGeometry()

    def _do_refresh_geometry(self):
        self.refreshGeometry(immediate=True)

    def refreshGeometry(self, immediate=False):

        if not immediate:

            if self._is_refreshing:
                if not self._refresh_timer.isActive():
                    self._refresh_timer.start(50)
                return

            if self._refresh_timer.isActive():
                return

            self._refresh_timer.start(50)
            return

        if self._refresh_timer.isActive():
            self._refresh_timer.stop()

        if self._is_refreshing:
            return

        self._is_refreshing = True
        self._apply_style()

        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        if not self.isVisible() or self._is_closing:
            self._is_refreshing = False
            return

        list1 = self.store.document.image_list1
        list2 = self.store.document.image_list2

        if not list1 and not list2:
            self._is_refreshing = False
            self.start_closing_animation()
            return

        if self.mode == FlyoutMode.DOUBLE:
            if not list1:
                self.mode = FlyoutMode.SINGLE_RIGHT
                self.source_list_num = 2
                self.panel_left.hide()
                self.panel_right.show()
                if self.main_window:
                    self.main_window.ui.combo_image1.setFlyoutOpen(False)
                    self.main_window.ui.combo_image2.setFlyoutOpen(True)
            elif not list2:
                self.mode = FlyoutMode.SINGLE_LEFT
                self.source_list_num = 1
                self.panel_right.hide()
                self.panel_left.show()
                if self.main_window:
                    self.main_window.ui.combo_image2.setFlyoutOpen(False)
                    self.main_window.ui.combo_image1.setFlyoutOpen(True)

        elif self.mode == FlyoutMode.SINGLE_LEFT and not list1:
            self.start_closing_animation()
            return
        elif self.mode == FlyoutMode.SINGLE_RIGHT and not list2:
            self.start_closing_animation()
            return

        h_left = self.panel_left.recalculate_and_set_height()
        h_right = self.panel_right.recalculate_and_set_height()

        if self.mode == FlyoutMode.DOUBLE:
            self.panel_left.show()
            self.panel_right.show()
            self._update_geometry_in_double_mode_internal()
        else:
            is_left = (self.mode in (FlyoutMode.SINGLE_LEFT, FlyoutMode.SINGLE_SIMPLE))
            active_panel = self.panel_left if is_left else self.panel_right
            anchor = self.main_window.ui.combo_image1 if is_left else self.main_window.ui.combo_image2
            active_list_num = 1 if is_left else 2

            active_panel.show()
            (self.panel_right if is_left else self.panel_left).hide()

            if hasattr(anchor, "setFlyoutOpen"):
                 anchor.setFlyoutOpen(True)

            panel_size = self._calc_panel_total_size(active_list_num)

            content_rect = self._calculate_ideal_content_geometry(anchor, panel_size, extra_y=self.SINGLE_APPEAR_EXTRA_Y)
            container_rect = content_rect.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)
            self.setGeometry(container_rect)

            self._apply_container_geometry()
            self._position_panels_for_single()

        self._apply_style()
        self._is_refreshing = False

    def populate(self, list_num: int, items: list, list_type="image", current_index=-1):
        panel = self.panel_left if (list_num == 1 or list_type == "simple") else self.panel_right

        if list_type == "simple":
            owner = self._owner_proxy_simple
        else:
            owner = self._owner_proxy_left if list_num == 1 else self._owner_proxy_right

        panel.clear_and_rebuild(items, owner, self.item_height, self.item_font, list_type, current_index)

        if self.mode == FlyoutMode.DOUBLE:

            self.refreshGeometry()

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
            self.main_controller.session_ctrl.remove_specific_image_from_list(list_num, index)

    def start_closing_animation(self):
        if not self.isVisible() or self._is_closing:
            return
        self.hide()

    def _on_animation_finished(self):
        if self._anim:
            self._anim.deleteLater()
            self._anim = None

    def hideEvent(self, event):
        if self._anim: self._anim.stop()
        PathTooltip.get_instance().hide_tooltip()

        self.last_close_timestamp = time.monotonic()

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
            result = self.panel_left if self.panel_left.isVisible() else (self.panel_right if self.panel_right.isVisible() else None)
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
