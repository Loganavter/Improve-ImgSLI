from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QMouseEvent, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from toolkit.widgets.atomic.simple_icon_button import SimpleIconButton
from toolkit.widgets.composite.color_options_flyout import ColorOptionsFlyout
from ui.icon_manager import AppIcon

class ColorSettingsButton(QWidget):

    smartColorSetRequested = pyqtSignal()
    colorOptionClicked = pyqtSignal(str)
    elementHovered = pyqtSignal(str)
    elementHoverEnded = pyqtSignal()

    def __init__(self, parent=None, current_language: str = "en", store=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.current_language = current_language
        self.store = store

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.button = SimpleIconButton(AppIcon.DIVIDER_COLOR, self)
        self.button.setFixedSize(36, 36)
        self.layout.addWidget(self.button)

        self.flyout = ColorOptionsFlyout(self.window(), current_language=self.current_language, store=self.store)
        self.flyout.hide()

        self.flyout.elementHovered.connect(self.elementHovered.emit)
        self.flyout.elementHoverEnded.connect(self.elementHoverEnded.emit)

        self.flyout_timer = QTimer(self)
        self.flyout_timer.setSingleShot(True)
        self.flyout_timer.setInterval(250)
        self.flyout_timer.timeout.connect(self._show_flyout)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(300)
        self.hide_timer.timeout.connect(self._check_and_hide_flyout)

        self.button.installEventFilter(self)
        self.flyout.installEventFilter(self)

        self.button.clicked.connect(self._on_button_clicked)

        self.flyout.colorOptionClicked.connect(self._on_flyout_option_clicked)

        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)

            self._update_underline_colors()

    def _on_button_clicked(self):

        self.smartColorSetRequested.emit()

    def _on_flyout_option_clicked(self, option):

        if hasattr(self.flyout, 'cancel_auto_hide'):
            self.flyout.cancel_auto_hide()
        self.colorOptionClicked.emit(option)
        self.flyout.hide()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:

            self.hide_timer.stop()
            self.flyout_timer.stop()
            self._show_flyout()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.LeftButton:

            local_pos = event.pos()
            if self.button.rect().contains(local_pos):
                self._on_button_clicked()
                event.accept()
                return
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.button:
            if event.type() == QEvent.Type.Enter:
                self.hide_timer.stop()

                if hasattr(self.flyout, 'cancel_auto_hide'):
                    self.flyout.cancel_auto_hide()
                self.flyout_timer.start()
            elif event.type() == QEvent.Type.Leave:
                self.flyout_timer.stop()

                if self.flyout.isVisible():
                    if hasattr(self.flyout, 'schedule_auto_hide'):
                        self.flyout.schedule_auto_hide(1000)
                else:
                    self.hide_timer.start()

        if obj is self.flyout:
            if event.type() == QEvent.Type.Enter:
                self.hide_timer.stop()

                if hasattr(self.flyout, 'cancel_auto_hide'):
                    self.flyout.cancel_auto_hide()
            elif event.type() == QEvent.Type.Leave:

                if hasattr(self.flyout, 'schedule_auto_hide'):
                    self.flyout.schedule_auto_hide(1000)
                else:
                    self.hide_timer.start()

        return super().eventFilter(obj, event)

    def _show_flyout(self):

        if hasattr(self.flyout, 'update_state'):
            self.flyout.update_state()

        if hasattr(self.flyout, 'cancel_auto_hide'):
            self.flyout.cancel_auto_hide()

        if hasattr(self.flyout, 'show_aligned'):
            self.flyout.show_aligned(self, "top")
        else:
            self.flyout.show_above(self)

    def _check_and_hide_flyout(self):
        if self.flyout.isVisible():
            try:
                cursor_pos = self.cursor().pos()
                if (not self.rect().contains(cursor_pos) and
                    not self.flyout.rect().contains(self.flyout.mapFromGlobal(self.cursor().pos()))):

                    if hasattr(self.flyout, 'cancel_auto_hide'):
                        self.flyout.cancel_auto_hide()
                    self.flyout.hide()
            except Exception:

                if hasattr(self.flyout, 'cancel_auto_hide'):
                    self.flyout.cancel_auto_hide()
                self.flyout.hide()

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        if hasattr(self.flyout, 'update_language'):
            self.flyout.update_language(lang_code)

    def set_store(self, store):

        if self.store:
            try:
                self.store.state_changed.disconnect(self._on_store_state_changed)
            except Exception:
                pass

        self.store = store
        if hasattr(self.flyout, 'store'):
            self.flyout.store = store

            if hasattr(self.flyout, 'update_state'):
                self.flyout.update_state()

        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)

            self._update_underline_colors()

    def _update_underline_colors(self):
        if not self.store:
            return

        vp = self.store.viewport

        use_mag = getattr(vp, "use_magnifier", False)

        if not use_mag:
            default_col = QColor(255, 255, 255, 100)
            self.button.set_color(default_col)
            return

        def _get_col(attr_name, default_alpha=255):
            col = getattr(vp, attr_name, QColor(255, 255, 255))
            c = QColor(col)

            c.setAlpha(default_alpha)
            return c

        col_capture = _get_col("capture_ring_color", 230)
        col_laser = _get_col("magnifier_laser_color", 230)
        col_border = _get_col("magnifier_border_color", 230)
        col_divider = _get_col("magnifier_divider_color", 230)

        is_combined = getattr(vp, "is_magnifier_combined", False)

        show_lasers = getattr(vp, "show_magnifier_guides", False)

        divider_visible_setting = getattr(vp, "magnifier_divider_visible", True)
        divider_thickness = getattr(vp, "magnifier_divider_thickness", 2)

        show_divider = is_combined and divider_visible_setting and (divider_thickness > 0)

        zones = [
            (True, col_capture),
            (show_lasers, col_laser),
            (True, col_border),
            (show_divider, col_divider),
        ]

        active_colors = [color for condition, color in zones if condition]

        self.button.set_color(active_colors)

    def _on_store_state_changed(self, domain: str):
        if domain in ("viewport", "settings"):
            self._update_underline_colors()

            if hasattr(self.flyout, 'update_state'):
                was_visible = self.flyout.isVisible()
                self.flyout.update_state()
                if was_visible:
                    self._reposition_flyout_if_visible()

    def _reposition_flyout_if_visible(self):
        if self.flyout.isVisible():
            if hasattr(self.flyout, 'show_aligned'):
                self.flyout.show_aligned(self, "top")
            else:
                self.flyout.show_above(self)

