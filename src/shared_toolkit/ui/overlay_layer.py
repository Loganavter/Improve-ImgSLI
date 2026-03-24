from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QWidget

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
        self._value_popups: dict[str, QLabel] = {}
        self._popup_timers: dict[str, QTimer] = {}
        self._host.installEventFilter(self)

    @property
    def host(self) -> QWidget:
        return self._host

    def attach(self, widget: QWidget):
        if widget is None or widget.parentWidget() is self._host:
            return

        was_visible = widget.isVisible()
        geometry = widget.geometry()
        widget.setParent(self._host)
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

    def ensure_visible(self, widget: QWidget, margin: int = 8):
        widget.setGeometry(self.clamp_rect(widget.geometry(), margin=margin))

    def contains_global(self, widget: QWidget, global_pos) -> bool:
        if widget is None or not widget.isVisible():
            return False
        return widget.rect().contains(widget.mapFromGlobal(global_pos))

    def _popup_label(self, key: str) -> QLabel:
        label = self._value_popups.get(key)
        if label is None:
            label = QLabel(self._host)
            label.setObjectName("ValuePopupLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.hide()
            self._value_popups[key] = label
        return label

    def _popup_timer(self, key: str) -> QTimer:
        timer = self._popup_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda popup_key=key: self.hide_popup(popup_key))
            self._popup_timers[key] = timer
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
        label = self._popup_label(key)
        if pixmap is not None:
            label.setText("")
            label.setPixmap(pixmap)
        else:
            label.setPixmap(QPixmap())
            label.setText(text)
        if size is not None:
            label.setFixedSize(size)
        else:
            label.adjustSize()

        label.style().unpolish(label)
        label.style().polish(label)
        label.update()
        label.setGeometry(
            self.place_rect_relative_to_anchor(
                anchor_widget,
                label.size(),
                position=position,
                offset=offset,
            )
        )
        label.show()
        label.raise_()

        timer = self._popup_timer(key)
        timer.stop()
        if timeout_ms > 0:
            timer.start(timeout_ms)

    def hide_popup(self, key: str):
        label = self._value_popups.get(key)
        if label is not None:
            label.hide()
        timer = self._popup_timers.get(key)
        if timer is not None:
            timer.stop()

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
