from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.constants import AppConstants
from domain.qt_adapters import color_to_qcolor
from shared_toolkit.ui.overlay_layer import get_overlay_layer
from shared_toolkit.ui.icon_manager import AppIcon
from shared_toolkit.ui.managers.flyout_timer_service import DelayedActionTimer
from shared_toolkit.ui.widgets.atomic.simple_icon_button import SimpleIconButton
from shared_toolkit.ui.widgets.atomic.tooltips import install_custom_tooltip
from shared_toolkit.ui.widgets.composite.color_options_flyout import ColorOptionsFlyout

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
        install_custom_tooltip(self)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.button = SimpleIconButton(AppIcon.DIVIDER_COLOR, self)
        self.button.setFixedSize(36, 36)
        self.layout.addWidget(self.button)

        self.flyout = ColorOptionsFlyout(
            self.window(), current_language=self.current_language, store=self.store
        )
        self.flyout.hide()

        self.flyout.elementHovered.connect(self.elementHovered.emit)
        self.flyout.elementHoverEnded.connect(self.elementHoverEnded.emit)

        self.flyout_timer = DelayedActionTimer(
            self._show_flyout,
            parent=self,
            interval_ms=AppConstants.TRANSIENT_FLYOUT_SHOW_DELAY_MS,
        )
        self.hide_timer = DelayedActionTimer(
            self._check_and_hide_flyout,
            parent=self,
            interval_ms=AppConstants.TRANSIENT_FLYOUT_HIDE_CHECK_DELAY_MS,
        )

        self.button.installEventFilter(self)
        self.flyout.installEventFilter(self)

        self.button.clicked.connect(self._on_button_clicked)

        self.flyout.colorOptionClicked.connect(self._on_flyout_option_clicked)

        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)

            self._update_underline_colors()

    def _ensure_overlay_parent(self):
        overlay_layer = get_overlay_layer(self)
        if overlay_layer is None:
            return
        if hasattr(self.flyout, "overlay_layer"):
            self.flyout.overlay_layer = overlay_layer
        if self.flyout.parentWidget() is not overlay_layer.host:
            overlay_layer.attach(self.flyout)

    def refresh_visual_state(self):
        self._update_underline_colors()
        if hasattr(self.flyout, "update_state"):
            self.flyout.update_state()

    def _on_button_clicked(self):

        self.smartColorSetRequested.emit()

    def _on_flyout_option_clicked(self, option):

        if hasattr(self.flyout, "cancel_auto_hide"):
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

                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
                self.flyout_timer.start()
            elif event.type() == QEvent.Type.Leave:
                self.flyout_timer.stop()

                if self.flyout.isVisible():
                    if hasattr(self.flyout, "schedule_auto_hide"):
                        self.flyout.schedule_auto_hide(
                            AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
                        )
                else:
                    self.hide_timer.start()

        if obj is self.flyout:
            if event.type() == QEvent.Type.Enter:
                self.hide_timer.stop()

                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
            elif event.type() == QEvent.Type.Leave:

                if hasattr(self.flyout, "schedule_auto_hide"):
                    self.flyout.schedule_auto_hide(
                        AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS
                    )
                else:
                    self.hide_timer.start()

        return super().eventFilter(obj, event)

    def _show_flyout(self):
        self._ensure_overlay_parent()

        if hasattr(self.flyout, "update_state"):
            self.flyout.update_state()

        if hasattr(self.flyout, "cancel_auto_hide"):
            self.flyout.cancel_auto_hide()

        if hasattr(self.flyout, "show_aligned"):
            self.flyout.show_aligned(self, "top")
        else:
            self.flyout.show_above(self)

    def _check_and_hide_flyout(self):
        if self.flyout.isVisible():
            try:
                cursor_pos = self.cursor().pos()
                inside_button = self.rect().contains(self.mapFromGlobal(cursor_pos))
                inside_flyout = self.flyout.rect().contains(
                    self.flyout.mapFromGlobal(cursor_pos)
                )
                if not inside_button and not inside_flyout:

                    if hasattr(self.flyout, "cancel_auto_hide"):
                        self.flyout.cancel_auto_hide()
                    self.flyout.hide()
            except Exception:

                if hasattr(self.flyout, "cancel_auto_hide"):
                    self.flyout.cancel_auto_hide()
                self.flyout.hide()

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        if hasattr(self.flyout, "update_language"):
            self.flyout.update_language(lang_code)

    def set_store(self, store):

        if self.store:
            try:
                self.store.state_changed.disconnect(self._on_store_state_changed)
            except Exception:
                pass

        self.store = store
        if hasattr(self.flyout, "store"):
            self.flyout.store = store

            if hasattr(self.flyout, "update_state"):
                self.flyout.update_state()

        if self.store:
            self.store.state_changed.connect(self._on_store_state_changed)

            self.refresh_visual_state()

    def _update_underline_colors(self):
        if not self.store:
            return

        vp = self.store.viewport

        use_mag = getattr(vp.view_state, "use_magnifier", False)

        if not use_mag:
            default_col = QColor(255, 255, 255, 100)
            self.button.set_color(default_col)
            return

        def _get_col(attr_name, default_alpha=255):
            col = getattr(vp.render_config, attr_name, QColor(255, 255, 255))
            c = color_to_qcolor(col) if hasattr(col, "r") else QColor(col)

            c.setAlpha(default_alpha)
            return c

        col_capture = _get_col("capture_ring_color", 230)
        col_laser = _get_col("magnifier_laser_color", 230)
        col_border = _get_col("magnifier_border_color", 230)
        col_divider = _get_col("magnifier_divider_color", 230)

        is_combined = getattr(vp.view_state, "is_magnifier_combined", False)

        show_lasers = getattr(vp.render_config, "show_magnifier_guides", False)

        divider_visible_setting = getattr(
            vp.render_config, "magnifier_divider_visible", True
        )
        divider_thickness = getattr(
            vp.render_config, "magnifier_divider_thickness", 2
        )

        show_divider = (
            is_combined and divider_visible_setting and (divider_thickness > 0)
        )

        zones = [
            (True, col_capture),
            (show_lasers, col_laser),
            (True, col_border),
            (show_divider, col_divider),
        ]

        active_colors = [color for condition, color in zones if condition]

        self.button.set_color(active_colors)

    def _on_store_state_changed(self, domain: str):
        if domain == "settings" or domain == "viewport" or domain.startswith("viewport."):
            self.refresh_visual_state()

            was_visible = self.flyout.isVisible()
            if was_visible:
                self._reposition_flyout_if_visible()

    def _reposition_flyout_if_visible(self):
        if self.flyout.isVisible():
            if hasattr(self.flyout, "show_aligned"):
                self.flyout.show_aligned(self, "top")
            else:
                self.flyout.show_above(self)
