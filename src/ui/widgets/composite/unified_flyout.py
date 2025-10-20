import logging
from enum import Enum

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
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from events.drag_drop_handler import DragAndDropService
from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
from src.shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from ui.widgets.custom_widgets import RatingListItem

logger = logging.getLogger("ImproveImgSLI")

_def_rect = lambda r: f"{r.x()},{r.y()} {r.width()}x{r.height()}"
_def_size = lambda s: f"{s.width()}x{s.height()}"

class FlyoutMode(Enum):
	HIDDEN = 0
	SINGLE_LEFT = 1
	SINGLE_RIGHT = 2
	DOUBLE = 3
	SINGLE_SIMPLE = 4

class _ListOwnerProxy:
	def __init__(self, image_number: int):
		self.image_number = image_number

class _PanelContent(QWidget):
	def __init__(self, owner_panel, parent=None):
		super().__init__(parent)
		self.owner_panel = owner_panel

	def paintEvent(self, event):
		super().paintEvent(event)
		if self.owner_panel.drop_indicator_y >= 0:
			painter = QPainter(self)
			pen_color = self.owner_panel.theme_manager.get_color("accent")
			pen = QPen(pen_color, 2, Qt.PenStyle.SolidLine)
			painter.setPen(pen)
			painter.drawLine(8, self.owner_panel.drop_indicator_y, self.width() - 8, self.owner_panel.drop_indicator_y)

class _Panel(QWidget):
	def __init__(self, app_ref, image_number: int, item_height: int, item_font, parent=None):
		super().__init__(parent)
		self.app_ref = app_ref
		self.image_number = image_number
		self.item_height = item_height
		self.item_font = item_font
		self.theme_manager = ThemeManager.get_instance()
		self.drop_indicator_y = -1
		self._container_height = 50
		self.placeholder_widget = None
		self.setObjectName("UnifiedFlyoutPanel")

		self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
		self.layout_outer = QVBoxLayout(self)
		self.layout_outer.setContentsMargins(0, 0, 0, 0)
		self.layout_outer.setSpacing(0)

		self.scroll_area = OverlayScrollArea(self)
		self.layout_outer.addWidget(self.scroll_area)

		self.content_widget = _PanelContent(self, self)
		self.content_layout = QVBoxLayout(self.content_widget)
		self.content_layout.setContentsMargins(4, 4, 4, 4)
		self.content_layout.setSpacing(2)
		self.scroll_area.setWidget(self.content_widget)

		self._apply_style()
		self.theme_manager.theme_changed.connect(self._apply_style)

	def sizeHint(self):
		try:
			width_hint = max(self.scroll_area.sizeHint().width(), 200)
		except Exception:
			width_hint = 200
		result = QSize(width_hint, self._container_height)
		return result

	def _apply_style(self):
		tm = self.theme_manager
		bg_color = tm.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
		border_color = tm.get_color("flyout.border").name(QColor.NameFormat.HexArgb)
		self.setStyleSheet(f"""
			#UnifiedFlyoutPanel {{
				background-color: {bg_color};
				border: 1px solid {border_color};
				border-radius: 8px;
			}}
		""")
		self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
		self.content_widget.setStyleSheet("background: transparent;")

	def clear_and_rebuild(self, image_list: list, owner_proxy: _ListOwnerProxy, item_height: int, item_font, list_type="image", current_index=-1):

		while item := self.content_layout.takeAt(0):
			if w := item.widget():
				w.deleteLater()
		self.placeholder_widget = None

		if current_index == -1:
			current_app_index = (
			 self.app_ref.app_state.current_index1 if self.image_number == 1 else self.app_ref.app_state.current_index2
			)
		else:
			current_app_index = current_index

		if not image_list:
			from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget
			ph = QWidget(self.content_widget)
			ph.setFixedHeight(item_height)
			ph.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
			hl = QHBoxLayout(ph)
			hl.setContentsMargins(8, 3, 8, 3)
			hl.setSpacing(8)
			lbl = QLabel("—", ph)
			lbl.setStyleSheet("color: rgba(255,255,255,0.4);")
			lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
			if item_font:
				lbl.setFont(item_font)
			hl.addWidget(lbl)
			self.content_layout.addWidget(ph)
			self.placeholder_widget = ph
			self.recalculate_and_set_height()
			return

		if list_type == "image":

			for i, item_data in enumerate(image_list):
				if len(item_data) >= 3:
					full_path, name, rating = item_data[1], item_data[2] or "-----", item_data[3]
				else:

					full_path = item_data[0] if len(item_data) > 0 else ""
					name = item_data[1] if len(item_data) > 1 else "-----"
					rating = item_data[2] if len(item_data) > 2 else 0

				list_item_widget = RatingListItem(
				 index=i, text=name, rating=rating, full_path=full_path,
				 app_ref=self.app_ref, owner_flyout=owner_proxy, parent=self.content_widget,
				 is_current=(i == current_app_index), item_height=item_height, item_font=item_font,
				)
				try:
					uf = self.app_ref.presenter.ui_manager.unified_flyout
					list_item_widget.itemSelected.connect(lambda idx=i, ln=self.image_number: uf._on_item_selected(ln, idx))
					list_item_widget.itemRightClicked.connect(lambda idx=i, ln=self.image_number: uf._on_item_right_clicked(ln, idx))
				except Exception:
					pass
				self.content_layout.addWidget(list_item_widget)
		else:

			for i, item_data in enumerate(image_list):
				if isinstance(item_data, (list, tuple)) and len(item_data) > 1:
					name = item_data[1]
				else:
					name = str(item_data)

				list_item_widget = RatingListItem(
				 index=i, text=name, parent=self.content_widget, item_type="simple",
				 is_current=(i == current_app_index), item_height=item_height, item_font=item_font
				)
				try:
					uf = self.app_ref.presenter.ui_manager.unified_flyout
					list_item_widget.itemSelected.connect(lambda idx=i, ln=self.image_number: uf._on_item_selected(ln, idx))
				except Exception:
					pass
				self.content_layout.addWidget(list_item_widget)

		self.recalculate_and_set_height()

	def recalculate_and_set_height(self):
		num_items = self.content_layout.count()
		if num_items == 0:
			min_empty = 50
			self._container_height = min_empty
			self.setFixedHeight(min_empty)
			self.scroll_area.custom_v_scrollbar.setVisible(False)
			return

		spacing = self.content_layout.spacing()
		content_height = num_items * self.item_height + max(0, num_items - 1) * spacing
		max_items_visible = 7.5
		max_content_height = int(max_items_visible * self.item_height)
		target_content_height = min(content_height, max_content_height)
		container_height = target_content_height + 4 + 4
		self._container_height = container_height
		self.setFixedHeight(container_height)

		self._check_scrollbar()

	def _check_scrollbar(self):
		content_h = self.content_widget.sizeHint().height()
		viewport_h = self.scroll_area.viewport().height()
		visible = content_h > viewport_h
		self.scroll_area.custom_v_scrollbar.setVisible(visible)

	def find_drop_target(self, local_pos_y: int, source_widget) -> tuple[int, int]:
		if self.content_layout.count() <= 1 and source_widget:
			return 0, 0
		closest_item = None
		min_distance = float('inf')
		for i in range(self.content_layout.count()):
			item = self.content_layout.itemAt(i).widget()
			if not item or item is source_widget or item is self.placeholder_widget:
				continue
			item_mid_y = item.y() + item.height() / 2
			distance = abs(local_pos_y - item_mid_y)
			if distance < min_distance:
				min_distance = distance
				closest_item = item
		if closest_item is None:
			return 0, 0
		closest_mid = closest_item.y() + closest_item.height() / 2
		closest_index = self.content_layout.indexOf(closest_item)
		if local_pos_y < closest_mid:
			return closest_index, closest_item.y()
		else:
			return closest_index + 1, closest_item.y() + closest_item.height()

	def can_accept_drop(self, payload: dict) -> bool:
		if not payload:
			return False
		return payload.get('list_num') == self.image_number

	def update_drop_indicator(self, global_pos: QPointF):
		local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
		_, indicator_y = self.find_drop_target(local_pos.y(), DragAndDropService.get_instance()._source_widget)
		if self.drop_indicator_y != indicator_y:
			self.drop_indicator_y = indicator_y
			self.content_widget.update()

	def clear_drop_indicator(self):
		if self.drop_indicator_y != -1:
			self.drop_indicator_y = -1
			self.content_widget.update()

	def handle_drop(self, payload: dict, global_pos: QPointF):
		self.clear_drop_indicator()
		source_list_num = payload.get('list_num', -1)
		source_index = payload.get('index', -1)
		if source_index == -1 or source_list_num == -1:
			return
		local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
		dest_index, _ = self.find_drop_target(local_pos.y(), DragAndDropService.get_instance()._source_widget)
		if source_list_num == self.image_number:
			QTimer.singleShot(0, lambda: self.app_ref.main_controller.reorder_item_in_list(
			 image_number=self.image_number,
			 source_index=source_index,
			 dest_index=dest_index
			))
		else:
			QTimer.singleShot(0, lambda: self.app_ref.main_controller.move_item_between_lists(
			 source_list_num=source_list_num,
			 source_index=source_index,
			 dest_list_num=self.image_number,
			 dest_index=dest_index
			))

class UnifiedFlyout(QWidget):
	item_chosen = pyqtSignal(int, int)
	closing_animation_finished = pyqtSignal()

	simple_item_chosen = pyqtSignal(int)

	SHADOW_RADIUS = 10
	MARGIN = 0
	SINGLE_APPEAR_EXTRA_Y = 6
	DOUBLE_CONTENT_EXTRA_Y = 6

	_move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS
	_move_easing = QEasingCurve.Type.OutQuad
	_drop_offset_px = 80

	def __init__(self, parent_widget):
		super().__init__(parent_widget)
		self.app_ref = parent_widget
		self.mode = FlyoutMode.HIDDEN
		self.source_list_num = 1
		self._is_closing = False
		self.item_height = 36
		self.item_font = None
		self._anim: QPropertyAnimation | None = None

		self._is_simple_mode = False

		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.container_widget = QWidget(self)
		self.container_widget.setObjectName("FlyoutWidget")
		shadow = QGraphicsDropShadowEffect(self)
		shadow.setBlurRadius(self.SHADOW_RADIUS)
		shadow.setOffset(1, 2)
		shadow.setColor(QColor(0, 0, 0, 120))
		self.container_widget.setGraphicsEffect(shadow)
		self.container_widget.setStyleSheet("background: transparent; border: none;")

		self.panel_left = _Panel(
		 self.app_ref, 1, self.item_height, self.item_font, self.container_widget
		)
		self.panel_right = _Panel(self.app_ref, 2, self.item_height, self.item_font, self.container_widget)

		self._owner_proxy_left = _ListOwnerProxy(1)
		self._owner_proxy_right = _ListOwnerProxy(2)

		self._owner_proxy_simple = _ListOwnerProxy(0)

		DragAndDropService.get_instance().register_drop_target(self)
		self.destroyed.connect(self._on_destroyed)
		self.theme_manager = ThemeManager.get_instance()
		self.theme_manager.theme_changed.connect(self._apply_style)
		self._apply_style()
		self.hide()

	def _on_animation_finished(self):
		if self._anim:
			anim_obj = self._anim
			self._anim = None
			anim_obj.deleteLater()

	def _apply_container_geometry(self):
		inner_rect = self.rect().adjusted(self.SHADOW_RADIUS, self.SHADOW_RADIUS, -self.SHADOW_RADIUS, -self.SHADOW_RADIUS)
		if self.container_widget.geometry() != inner_rect:
			self.container_widget.setGeometry(inner_rect)

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self._apply_container_geometry()
		if self.mode != FlyoutMode.DOUBLE:
			self._position_panels_for_single()

	def _apply_style(self):
		self.setStyleSheet("background: transparent;")

	def _on_destroyed(self):
		try:
			DragAndDropService.get_instance().unregister_drop_target(self)
		except Exception:
			pass

	def showAsSingle(self, list_num: int, anchor_widget: QWidget, list_type="image", simple_items=None, simple_current_index=-1):

		if self._anim:
			self._anim.stop()

		self.source_list_num = list_num
		self._is_simple_mode = (list_type == "simple")

		if self._is_simple_mode:
			self.mode = FlyoutMode.SINGLE_SIMPLE
		else:
			self.mode = FlyoutMode.SINGLE_LEFT if list_num == 1 else FlyoutMode.SINGLE_RIGHT

		btn = anchor_widget
		self.item_height = btn.getItemHeight() if hasattr(btn, 'getItemHeight') else 34
		self.item_font = btn.getItemFont() if hasattr(btn, 'getItemFont') else QApplication.font()

		self.panel_left.item_height = self.item_height
		self.panel_left.item_font = self.item_font
		self.panel_right.item_height = self.item_height
		self.panel_right.item_font = self.item_font

		panel = self.panel_left if list_num == 1 or self._is_simple_mode else self.panel_right

		if self._is_simple_mode:
			self.populate(0, simple_items, list_type="simple", current_index=simple_current_index)
			self.panel_left.setVisible(True)
			self.panel_right.setVisible(False)
		else:
			self.populate(1, self.app_ref.app_state.image_list1, current_index=self.app_ref.app_state.current_index1)
			self.populate(2, self.app_ref.app_state.image_list2, current_index=self.app_ref.app_state.current_index2)
			self.panel_left.setVisible(list_num == 1)
			self.panel_right.setVisible(list_num == 2)

		ideal_geom = self._calculate_ideal_geometry(anchor_widget, panel.sizeHint())

		end_pos = ideal_geom.topLeft()
		end_pos.setY(end_pos.y() + self.SINGLE_APPEAR_EXTRA_Y)
		start_pos = QPoint(end_pos.x(), end_pos.y() - self._drop_offset_px)

		self.resize(ideal_geom.size())
		self.move(start_pos)
		self._apply_container_geometry()
		self._position_panels_for_single()
		self.show()
		self.raise_()

		anim_pos = QPropertyAnimation(self, b"pos", self)
		anim_pos.setDuration(self._move_duration_ms)
		anim_pos.setStartValue(start_pos)
		anim_pos.setEndValue(end_pos)
		anim_pos.setEasingCurve(self._move_easing)

		anim_pos.finished.connect(self._on_animation_finished)
		self._anim = anim_pos
		anim_pos.start()

	def switchToDoubleMode(self):
		if self.mode == FlyoutMode.DOUBLE or not self.isVisible() or self._is_simple_mode:
			return

		if self._anim and hasattr(self._anim, 'state'):
			try:
				if self._anim.state() == QPropertyAnimation.State.Running:
					self._anim.stop()
			except Exception:
				pass

		self.mode = FlyoutMode.DOUBLE
		self.panel_left.show()
		self.panel_right.show()

		button1 = self.app_ref.ui.combo_image1
		button2 = self.app_ref.ui.combo_image2

		left_size = self._calc_panel_total_size(1)
		right_size = self._calc_panel_total_size(2)

		geom1_content_only = self._calculate_ideal_geometry(button1, left_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
		geom2_content_only = self._calculate_ideal_geometry(button2, right_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)

		unified_content = geom1_content_only.united(geom2_content_only)
		final_unified_geom = unified_content.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)

		panel1_local_geom = geom1_content_only.translated(-unified_content.topLeft())
		panel2_local_geom = geom2_content_only.translated(-unified_content.topLeft())

		self.setGeometry(final_unified_geom)
		self._apply_container_geometry()
		self._apply_panel_geometries(panel1_local_geom, panel2_local_geom)

	def _apply_panel_geometries(self, local1: QRect, local2: QRect):
		self.panel_left.setGeometry(local1)
		self.panel_right.setGeometry(local2)
		try:
			self.panel_left._check_scrollbar()
			self.panel_right._check_scrollbar()
		except Exception:
			pass

	def _position_panels_for_single(self):
		inner_rect = self.container_widget.rect()
		self.panel_left.setGeometry(inner_rect)
		self.panel_right.setGeometry(inner_rect)

	def _calc_panel_total_size(self, list_num: int) -> QSize:
		panel = self.panel_left if list_num == 1 else self.panel_right
		panel.adjustSize()
		related_button = (
		 self.app_ref.ui.combo_image1 if list_num == 1 else self.app_ref.ui.combo_image2
		)

		w = max(panel.sizeHint().width(), related_button.width(), 200)
		h = panel.sizeHint().height()
		result = QSize(w, h)
		return result

	def _calculate_ideal_geometry(self, anchor_widget: QWidget, panel_size: QSize, content_only=False) -> QRect:
		button_pos_relative = anchor_widget.mapTo(self.parent(), QPoint(0, 0))

		content_width = max(anchor_widget.width(), panel_size.width())
		content_height = panel_size.height()

		content_x = button_pos_relative.x()
		content_y = button_pos_relative.y() + anchor_widget.height() - 4

		content_rect = QRect(content_x, content_y, content_width, content_height)

		if content_only:
			return content_rect

		full_rect = content_rect.adjusted(
		 -self.SHADOW_RADIUS,
		 -self.SHADOW_RADIUS,
		 self.SHADOW_RADIUS,
		 self.SHADOW_RADIUS,
		)
		return full_rect

	def populate(self, list_num: int, items: list, list_type="image", current_index=-1):
		panel = self.panel_left if list_num == 1 or list_type == "simple" else self.panel_right

		if list_type == "simple":
			owner = self._owner_proxy_simple
		else:
			owner = self._owner_proxy_left if list_num == 1 else self._owner_proxy_right

		panel.clear_and_rebuild(items, owner, self.item_height, self.item_font, list_type, current_index)

	def update_item_rating(self, list_num: int, index: int, new_rating: int):
		try:
			panel = self.panel_left if list_num == 1 else self.panel_right
			if not panel:
				return
			for i in range(panel.content_layout.count()):
				item = panel.content_layout.itemAt(i)
				w = item.widget() if item else None
				if isinstance(w, RatingListItem) and getattr(w, 'index', None) == index:
					w.rating_label.setText(str(new_rating))
					w.update()
					break
		except Exception:
			pass

	def _on_item_selected(self, list_num: int, index: int):

		if self._is_simple_mode:
			self.simple_item_chosen.emit(index)
		else:
			if list_num == 1:
				self.app_ref.app_state.current_index1 = index
			else:
				self.app_ref.app_state.current_index2 = index
			self.app_ref.main_controller.set_current_image(list_num)
			self.item_chosen.emit(list_num, index)

		self.start_closing_animation()

	def start_closing_animation(self):

		if not self.isVisible() or self._is_closing:
			return
		self.hide()

	def hideEvent(self, event):

		if self._anim:
			self._anim.stop()

		if not self._is_closing:
			self._is_closing = True
			try:
				self.mode = FlyoutMode.HIDDEN
				self.closing_animation_finished.emit()
			finally:
				self._is_closing = False

		super().hideEvent(event)

	def updateGeometryInDoubleMode(self):
		if self.mode != FlyoutMode.DOUBLE or not self.isVisible():
			return
		button1 = self.app_ref.ui.combo_image1
		button2 = self.app_ref.ui.combo_image2
		left_size = self._calc_panel_total_size(1)
		right_size = self._calc_panel_total_size(2)
		geom1_content_only = self._calculate_ideal_geometry(button1, left_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
		geom2_content_only = self._calculate_ideal_geometry(button2, right_size, content_only=True).translated(0, self.DOUBLE_CONTENT_EXTRA_Y)
		unified_content = geom1_content_only.united(geom2_content_only)
		final_unified_geom = unified_content.adjusted(-self.SHADOW_RADIUS, -self.SHADOW_RADIUS, self.SHADOW_RADIUS, self.SHADOW_RADIUS)
		panel1_local_geom = geom1_content_only.translated(-unified_content.topLeft())
		panel2_local_geom = geom2_content_only.translated(-unified_content.topLeft())
		self.setGeometry(final_unified_geom)
		self._apply_container_geometry()
		self._apply_panel_geometries(panel1_local_geom, panel2_local_geom)

	def can_accept_drop(self, payload: dict) -> bool:
		if not payload:
			return False
		return self.isVisible()

	def _panel_under_global_pos(self, global_pos: QPointF):

		local = self.mapFromGlobal(global_pos.toPoint())

		container_local = self.container_widget.mapFrom(self, local)

		if self.mode == FlyoutMode.DOUBLE:
			if self.panel_left.geometry().contains(container_local):
				return self.panel_left
			if self.panel_right.geometry().contains(container_local):
				return self.panel_right

			return None
		else:

			return self.panel_left if self.panel_left.isVisible() else (self.panel_right if self.panel_right.isVisible() else None)

	def update_drop_indicator(self, global_pos: QPointF):
		panel = self._panel_under_global_pos(global_pos)
		if panel is None:

			try:
				self.panel_left.clear_drop_indicator()
				self.panel_right.clear_drop_indicator()
			except Exception:
				pass
			return

		other = self.panel_right if panel is self.panel_left else self.panel_left
		try:
			panel.update_drop_indicator(global_pos)
			other.clear_drop_indicator()
		except Exception:
			pass

	def clear_drop_indicator(self):
		try:
			self.panel_left.clear_drop_indicator()
			self.panel_right.clear_drop_indicator()
		except Exception:
			pass

	def handle_drop(self, payload: dict, global_pos: QPointF):
		panel = self._panel_under_global_pos(global_pos)
		if panel is None:
			return
		panel.handle_drop(payload, global_pos)
