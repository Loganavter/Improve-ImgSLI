from PyQt6.QtCore import pyqtSignal, QEvent, Qt, QSize, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QWidget
from PyQt6.QtGui import QColor

from toolkit.widgets.atomic.simple_icon_button import SimpleIconButton
from toolkit.widgets.composite.base_flyout import BaseFlyout
from ui.icon_manager import AppIcon
from resources.translations import tr

class ColorOptionsFlyout(BaseFlyout):
    colorOptionClicked = pyqtSignal(str)
    elementHovered = pyqtSignal(str)
    elementHoverEnded = pyqtSignal()

    def __init__(self, parent=None, current_language: str = "en", store=None):
        super().__init__(parent)
        self.current_language = current_language
        self.store = store
        self._hovered_element = None
        self._anchor_button = None

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide_timeout)

        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(6)

        self.content_layout.addLayout(self.h_layout)

        self.btn_disabled = SimpleIconButton(AppIcon.DIVIDER_HIDDEN, self.container)
        self.btn_disabled.setFixedSize(28, 28)
        self.btn_disabled.setIconSize(QSize(18, 18))
        self.btn_disabled.setEnabled(False)
        self.btn_disabled.setStyleSheet("opacity: 0.4;")
        self.btn_disabled.setToolTip(tr("magnifier.change_magnifier_colors", self.current_language))
        self.h_layout.addWidget(self.btn_disabled)

        self.btn_capture = SimpleIconButton(AppIcon.CAPTURE_AREA_COLOR, self.container)
        self.btn_capture.setFixedSize(28, 28)
        self.btn_capture.setIconSize(QSize(18, 18))
        self.btn_capture.setToolTip(tr("magnifier.capture_ring", self.current_language))
        self.btn_capture.clicked.connect(lambda: self.colorOptionClicked.emit("capture"))
        self.btn_capture.installEventFilter(self)
        self.btn_capture.setProperty("element_name", "capture")
        self.h_layout.addWidget(self.btn_capture)

        self.btn_laser = SimpleIconButton(AppIcon.MAGNIFIER_GUIDES, self.container)
        self.btn_laser.setFixedSize(28, 28)
        self.btn_laser.setIconSize(QSize(18, 18))
        self.btn_laser.setToolTip(tr("label.guides", self.current_language))
        self.btn_laser.clicked.connect(lambda: self.colorOptionClicked.emit("laser"))
        self.btn_laser.installEventFilter(self)
        self.btn_laser.setProperty("element_name", "laser")
        self.h_layout.addWidget(self.btn_laser)

        self.btn_border = SimpleIconButton(AppIcon.MAGNIFIER_BORDER_COLOR, self.container)
        self.btn_border.setFixedSize(28, 28)
        self.btn_border.setIconSize(QSize(18, 18))
        self.btn_border.setToolTip(tr("label.border", self.current_language))
        self.btn_border.clicked.connect(lambda: self.colorOptionClicked.emit("border"))
        self.btn_border.installEventFilter(self)
        self.btn_border.setProperty("element_name", "border")
        self.h_layout.addWidget(self.btn_border)

        self.btn_divider = SimpleIconButton(AppIcon.VERTICAL_SPLIT, self.container)
        self.btn_divider.setFixedSize(28, 28)
        self.btn_divider.setIconSize(QSize(18, 18))
        self.btn_divider.setToolTip(tr("ui.choose_magnifier_divider_line_color", self.current_language))
        self.btn_divider.clicked.connect(lambda: self.colorOptionClicked.emit("divider"))
        self.btn_divider.installEventFilter(self)
        self.btn_divider.setProperty("element_name", "divider")
        self.h_layout.addWidget(self.btn_divider)

        self._update_buttons_visibility()

    def _is_magnifier_active(self):
        if not self.store:
            return False
        return getattr(self.store.viewport, "use_magnifier", False)

    def _is_capture_active(self):
        if not self._is_magnifier_active():
            return False
        return getattr(self.store.viewport, "show_capture_area_on_main_image", True)

    def _is_laser_active(self):
        if not self._is_magnifier_active():
            return False
        return getattr(self.store.viewport, "show_magnifier_guides", False)

    def _is_divider_active(self):

        if not self._is_magnifier_active():
            return False
        return getattr(self.store.viewport, "is_magnifier_combined", False)

    def _update_buttons_visibility(self):
        is_magnifier_active = self._is_magnifier_active()

        if not is_magnifier_active:
            self.btn_disabled.setVisible(True)
            self.btn_capture.setVisible(False)
            self.btn_border.setVisible(False)
            self.btn_laser.setVisible(False)
            self.btn_divider.setVisible(False)
        else:
            self.btn_disabled.setVisible(False)
            self.btn_capture.setVisible(self._is_capture_active())
            self.btn_border.setVisible(True)
            self.btn_laser.setVisible(self._is_laser_active())
            self.btn_divider.setVisible(self._is_divider_active())

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            element_name = obj.property("element_name")
            if element_name and element_name != self._hovered_element:
                self._hovered_element = element_name
                self.elementHovered.emit(element_name)
        elif event.type() == QEvent.Type.Leave:
            if self._hovered_element:
                self._hovered_element = None
                self.elementHoverEnded.emit()

        return super().eventFilter(obj, event)

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.btn_disabled.setToolTip(tr("magnifier.change_magnifier_colors", self.current_language))
        self.btn_capture.setToolTip(tr("magnifier.capture_ring", self.current_language))
        self.btn_border.setToolTip(tr("label.border", self.current_language))
        self.btn_laser.setToolTip(tr("label.guides", self.current_language))
        self.btn_divider.setToolTip(tr("ui.choose_magnifier_divider_line_color", self.current_language))

    def update_state(self):
        self._update_buttons_visibility()

        self.h_layout.invalidate()
        self.h_layout.activate()

        self.container.updateGeometry()
        self.updateGeometry()

        self.adjustSize()

    def show_above(self, anchor):

        self.update_state()
        self._anchor_button = anchor
        self.show_aligned(anchor, "top")

    def schedule_auto_hide(self, ms: int):
        if ms <= 0:
            self._auto_hide_timer.stop()
            return
        self._auto_hide_timer.start(ms)

    def cancel_auto_hide(self):
        self._auto_hide_timer.stop()

    def _on_auto_hide_timeout(self):
        if not self.isVisible():
            return

        from PyQt6.QtGui import QCursor
        from PyQt6.QtCore import QPoint
        cursor_pos = QCursor.pos()

        try:
            flyout_global_rect = self.geometry()
            if flyout_global_rect.contains(cursor_pos):

                self.schedule_auto_hide(1000)
                return
        except Exception:
            pass

        if self._anchor_button:
            try:
                button_global_pos = self._anchor_button.mapToGlobal(QPoint(0, 0))
                button_rect = self._anchor_button.rect()
                button_global_rect = button_rect.translated(button_global_pos)
                if button_global_rect.contains(cursor_pos):

                    self.schedule_auto_hide(1000)
                    return
            except Exception:
                pass

        self.hide()

    def hide(self):
        self.cancel_auto_hide()
        super().hide()

