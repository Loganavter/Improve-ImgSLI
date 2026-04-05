from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from shared_toolkit.ui.widgets.helpers import draw_rounded_shadow

class _PopupBubble(QWidget):
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 6

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        self._layout.setSpacing(0)

        self.label = QLabel(self)
        self.label.setObjectName("ValuePopupLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.label)
        self.hide()

    def set_content(
        self,
        *,
        text: str = "",
        pixmap: QPixmap | None = None,
        size: QSize | None = None,
    ) -> None:
        if pixmap is not None:
            self.label.setText("")
            self.label.setPixmap(pixmap)
        else:
            self.label.setPixmap(QPixmap())
            self.label.setText(text)

        if size is not None:
            self.label.setFixedSize(size)
        else:
            self.label.adjustSize()

        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_rounded_shadow(
            painter,
            self.label.geometry(),
            steps=self.SHADOW_RADIUS,
            radius=self.CONTENT_RADIUS,
        )
        painter.end()

def get_overlay_layer(widget: QWidget | None):
    current = widget
    while current is not None:
        overlay = getattr(current, "overlay_layer", None)
        if overlay is not None:
            return overlay
        current = current.parentWidget()

    if widget is not None:
        window = widget.window()
        return getattr(window, "overlay_layer", None)
    return None

class OverlayLayer(QObject):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._value_popups: dict[str, _PopupBubble] = {}
        self._popup_timers: dict[str, QTimer] = {}
        self._host.installEventFilter(self)

    @staticmethod
    def _is_deleted(obj) -> bool:
        return obj is None or sip.isdeleted(obj)

    @property
    def host(self) -> QWidget:
        return self._host

    def attach(self, widget: QWidget):
        if widget is None or widget.parentWidget() is self._host:
            resource_manager = getattr(self._host, "ui_resource_manager", None)
            if resource_manager is not None and widget is not None:
                resource_manager.register_widget(
                    widget,
                    name=f"overlay:{type(widget).__name__}",
                )
            return

        was_visible = widget.isVisible()
        geometry = widget.geometry()
        widget.setParent(self._host)
        resource_manager = getattr(self._host, "ui_resource_manager", None)
        if resource_manager is not None:
            resource_manager.register_widget(
                widget,
                name=f"overlay:{type(widget).__name__}",
            )
        if geometry.isValid():
            widget.setGeometry(geometry)
        if was_visible:
            widget.show()
            widget.raise_()
        else:
            widget.hide()

    def anchor_rect(self, anchor_widget: QWidget) -> QRect:
        top_left = anchor_widget.mapTo(self._host, QPoint(0, 0))
        return QRect(top_left, anchor_widget.size())

    def anchor_global_rect(self, anchor_widget: QWidget) -> QRect:
        top_left = anchor_widget.mapToGlobal(QPoint(0, 0))
        return QRect(top_left, anchor_widget.size())

    def clamp_rect(self, rect: QRect, margin: int = 8) -> QRect:
        bounds = self._host.rect().adjusted(margin, margin, -margin, -margin)
        if bounds.width() <= 0 or bounds.height() <= 0:
            return rect

        width = min(rect.width(), bounds.width())
        height = min(rect.height(), bounds.height())
        x = max(bounds.left(), min(rect.x(), bounds.right() - width + 1))
        y = max(bounds.top(), min(rect.y(), bounds.bottom() - height + 1))
        return QRect(x, y, width, height)

    def place_rect_relative_to_anchor(
        self,
        anchor_widget: QWidget,
        size: QSize,
        position: str = "top",
        offset: int = 6,
        margin: int = 8,
    ) -> QRect:
        anchor_rect = self.anchor_rect(anchor_widget)

        if position == "bottom":
            x = anchor_rect.x() + (anchor_rect.width() - size.width()) // 2
            y = anchor_rect.bottom() + 1 + offset
        elif position == "left-top":
            x = anchor_rect.left() - size.width() - offset
            y = anchor_rect.top() - size.height() - offset
        else:
            x = anchor_rect.x() + (anchor_rect.width() - size.width()) // 2
            y = anchor_rect.y() - size.height() - offset

        return self.clamp_rect(QRect(x, y, size.width(), size.height()), margin=margin)

    def place_global_rect_relative_to_anchor(
        self,
        anchor_widget: QWidget,
        size: QSize,
        position: str = "top",
        offset: int = 6,
        margin: int = 8,
    ) -> QRect:
        anchor_rect = self.anchor_global_rect(anchor_widget)
        host_window = self._host.window()
        bounds = host_window.frameGeometry().adjusted(margin, margin, -margin, -margin)

        if position == "bottom":
            x = anchor_rect.x() + (anchor_rect.width() - size.width()) // 2
            y = anchor_rect.bottom() + 1 + offset
        elif position == "left-top":
            x = anchor_rect.left() - size.width() - offset
            y = anchor_rect.top() - size.height() - offset
        else:
            x = anchor_rect.x() + (anchor_rect.width() - size.width()) // 2
            y = anchor_rect.y() - size.height() - offset

        width = min(size.width(), bounds.width())
        height = min(size.height(), bounds.height())
        x = max(bounds.left(), min(x, bounds.right() - width + 1))
        y = max(bounds.top(), min(y, bounds.bottom() - height + 1))
        return QRect(x, y, width, height)

    def ensure_visible(self, widget: QWidget, margin: int = 8):
        widget.setGeometry(self.clamp_rect(widget.geometry(), margin=margin))

    def contains_global(self, widget: QWidget, global_pos) -> bool:
        if widget is None or not widget.isVisible():
            return False
        return widget.rect().contains(widget.mapFromGlobal(global_pos))

    def _popup_label(self, key: str) -> _PopupBubble:
        popup = self._value_popups.get(key)
        if popup is not None:
            if self._is_deleted(popup):
                self._forget_popup(key)
                popup = None
        if popup is not None:
            try:
                popup.parentWidget()
            except RuntimeError:
                self._forget_popup(key)
                popup = None
        if popup is None:
            popup = _PopupBubble(self._host.window())
            popup.hide()
            self._value_popups[key] = popup
            popup.destroyed.connect(lambda *_args, popup_key=key: self._forget_popup(popup_key))
            resource_manager = getattr(self._host, "ui_resource_manager", None)
            if resource_manager is not None:
                resource_manager.register_widget(
                    popup,
                    name=f"overlay_popup:{key}",
                )
        return popup

    def _popup_timer(self, key: str) -> QTimer:
        timer = self._popup_timers.get(key)
        if timer is not None and self._is_deleted(timer):
            self._popup_timers.pop(key, None)
            timer = None
        if timer is not None:
            try:
                timer.parent()
            except RuntimeError:
                self._popup_timers.pop(key, None)
                timer = None
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda popup_key=key: self.hide_popup(popup_key))
            self._popup_timers[key] = timer
            timer.destroyed.connect(lambda *_args, popup_key=key: self._popup_timers.pop(popup_key, None))
        return timer

    def show_popup(
        self,
        key: str,
        anchor_widget: QWidget,
        *,
        text: str = "",
        pixmap: QPixmap | None = None,
        size: QSize | None = None,
        position: str = "top",
        offset: int = 6,
        timeout_ms: int = 800,
    ):
        popup = self._popup_label(key)
        try:
            popup.set_content(text=text, pixmap=pixmap, size=size)

            popup.label.style().unpolish(popup.label)
            popup.label.style().polish(popup.label)
            popup.label.update()
            popup.setGeometry(
                self.place_global_rect_relative_to_anchor(
                    anchor_widget,
                    popup.size(),
                    position=position,
                    offset=offset,
                )
            )
            popup.show()
            popup.raise_()
        except RuntimeError:
            self._forget_popup(key)
            return

        timer = self._popup_timer(key)
        if self._is_deleted(timer):
            self._popup_timers.pop(key, None)
            return
        timer.stop()
        if timeout_ms > 0:
            timer.start(timeout_ms)

    def _forget_popup(self, key: str):
        self._value_popups.pop(key, None)
        timer = self._popup_timers.pop(key, None)
        if timer is not None and not self._is_deleted(timer):
            try:
                timer.stop()
            except RuntimeError:
                pass

    def hide_popup(self, key: str):
        popup = self._value_popups.get(key)
        if popup is not None and self._is_deleted(popup):
            self._value_popups.pop(key, None)
            popup = None
        if popup is not None:
            try:
                popup.hide()
            except RuntimeError:
                pass
        timer = self._popup_timers.get(key)
        if timer is not None and self._is_deleted(timer):
            self._popup_timers.pop(key, None)
            timer = None
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                self._popup_timers.pop(key, None)
        if popup is None:
            self._forget_popup(key)
            return
        try:
            popup.parentWidget()
        except RuntimeError:
            self._forget_popup(key)

    def hide_all_popups(self):
        for key in list(self._value_popups.keys()):
            self.hide_popup(key)

    def eventFilter(self, watched, event):
        if watched is self._host:
            if event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Move,
                QEvent.Type.Hide,
                QEvent.Type.Close,
                QEvent.Type.WindowStateChange,
                QEvent.Type.Leave,
            ):
                self.hide_all_popups()
        return super().eventFilter(watched, event)
