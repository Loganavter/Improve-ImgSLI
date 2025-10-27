import time
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from ui.widgets.atomic.numbered_toggle_icon_button import NumberedToggleIconButton
from shared_toolkit.ui.managers.theme_manager import ThemeManager

class MagnifierVisibilityFlyout(QWidget):
    """
    Небольшой флайаут поверх кнопки лупы: 2 или 3 мини‑кнопки [1][2][3].
    - 1 = левая/верхняя лупа
    - 2 = центральная (дифф)
    - 3 = правая/нижняя

    Расширенная зона взаимодействия: геометрия флайаута может включать "пустой" участок,
    дотягивающийся до нижней кромки родительской кнопки. Само содержимое (кнопки) размещается сверху.
    """
    def __init__(self, parent_widget: QWidget):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._panel = QWidget(self)
        self._panel.setObjectName("MagnifierVisibilityFlyoutPanel")
        self._layout = QHBoxLayout(self._panel)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(6)

        self.btn_left = NumberedToggleIconButton(1, self._panel)
        self.btn_center = NumberedToggleIconButton(2, self._panel)
        self.btn_right = NumberedToggleIconButton(3, self._panel)

        for b in (self.btn_left, self.btn_center, self.btn_right):
            self._layout.addWidget(b)

        self._count = 3
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide_timeout)

        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()
        self.hide()

    def _apply_style(self):

        try:
            is_dark = self._theme_manager.is_dark() if hasattr(self._theme_manager, "is_dark") else False
        except Exception:
            is_dark = False
        bg_color = "#3c3c3c" if is_dark else "#ffffff"
        border_color = "#666666" if is_dark else "#d0d0d0"
        self._panel.setStyleSheet(f"""
            #MagnifierVisibilityFlyoutPanel {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def set_mode_and_states(self, show_center: bool, left_on: bool, center_on: bool, right_on: bool):
        """
        Контролирует набор кнопок (2 или 3) и их состояние.
        show_center=True => отображаем 3 кнопки, иначе 2 (левая/правая).
        Инвертируем семантику checked: checked=True => OFF (выключено), checked=False => ON (включено).
        """
        self._count = 3 if show_center else 2
        self.btn_center.setVisible(show_center)

        self.btn_left.setChecked(not left_on, emit_signal=False)
        self.btn_right.setChecked(not right_on, emit_signal=False)
        if show_center:
            self.btn_center.setChecked(not center_on, emit_signal=False)

        self.update_display_numbers(left_on, center_on, right_on, show_center)

        self._panel.adjustSize()
        self.adjustSize()

    def update_display_numbers(self, left_on: bool, center_on: bool, right_on: bool, show_center: bool):
        """
        Сжимает нумерацию только для активных (ON) луп слева направо.
        - Активные получают номера 1..N
        - Выключенные (OFF) — без номера (пусто), остаются видимыми как "выключенные"
        """

        self.btn_left.set_display_number(None)
        self.btn_center.set_display_number(None)
        self.btn_right.set_display_number(None)

        next_num = 1

        if left_on:
            self.btn_left.set_display_number(next_num)
            next_num += 1

        if show_center:
            if center_on:
                self.btn_center.set_display_number(next_num)
                next_num += 1
            else:

                self.btn_center.set_display_number(None)

        if right_on:
            self.btn_right.set_display_number(next_num)
            next_num += 1
    def show_for_button(self, anchor_btn: QWidget, parent_widget: QWidget, hover_delay_ms: int = 0):
        """
        Позиционирует флайаут над кнопкой anchor_btn.
        Без расширенной зоны: геометрия равна размеру панели; кнопки "летают" на одной линии.
        """

        btn_top_left_in_parent = anchor_btn.mapTo(parent_widget, QPoint(0, 0))
        btn_w = anchor_btn.width()
        btn_h = anchor_btn.height()

        self._panel.adjustSize()
        panel_w = self._panel.width()
        panel_h = self._panel.height()

        target_x = int(btn_top_left_in_parent.x() + (btn_w - panel_w) // 2)
        target_y = int(btn_top_left_in_parent.y() - panel_h - 6)

        self.setGeometry(QRect(target_x, target_y, max(1, panel_w), max(1, panel_h)))
        self._panel.setGeometry(QRect(0, 0, panel_w, panel_h))

        if hover_delay_ms > 0:
            QTimer.singleShot(hover_delay_ms, self._do_show_safe)
        else:
            self._do_show_safe()

    def _do_show_safe(self):
        self.show()
        self.raise_()

    def schedule_auto_hide(self, ms: int):
        if ms <= 0:
            self._auto_hide_timer.stop()
            return
        self._auto_hide_timer.start(ms)

    def cancel_auto_hide(self):
        self._auto_hide_timer.stop()

    def _on_auto_hide_timeout(self):
        self.hide()

    def contains_global(self, global_pos) -> bool:

        return self.geometry().contains(self.parent().mapFromGlobal(global_pos).toPoint())
