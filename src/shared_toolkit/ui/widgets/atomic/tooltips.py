from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from ...overlay_layer import get_overlay_layer
from ...managers.theme_manager import ThemeManager

class PathTooltip(QObject):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PathTooltip()
        return cls._instance

    def __init__(self):
        if PathTooltip._instance is not None:
            raise RuntimeError("Singleton")
        super().__init__(None)
        self._label: QLabel | None = None
        self._host: QWidget | None = None
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)

    def _resolve_host(self, global_pos: QPoint) -> QWidget | None:
        app = QApplication.instance()
        if app is None:
            return None

        widget = QApplication.widgetAt(global_pos)
        if widget is None:
            widget = app.activeWindow()
        if widget is None:
            widgets = app.topLevelWidgets()
            widget = widgets[-1] if widgets else None
        if widget is None:
            return None

        overlay = get_overlay_layer(widget)
        if overlay is not None:
            return overlay.host
        return widget.window()

    def _ensure_label(self, host: QWidget) -> QLabel:
        if self._label is not None and self._host is host:
            return self._label

        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except Exception:
                pass

        if self._label is None:
            self._label = QLabel(host)
            self._label.setObjectName("TooltipContentWidget")
            self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._label.hide()
        else:
            self._label.setParent(host)

        self._host = host
        self._host.installEventFilter(self)
        self._apply_style()
        return self._label

    def _apply_style(self):
        if self._label is None:
            return
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
        self._label.update()

    def show_tooltip(self, pos: QPoint, text: str):
        if not text:
            return

        host = self._resolve_host(pos)
        if host is None:
            return

        label = self._ensure_label(host)
        label.setText(text)
        label.adjustSize()

        local_pos = host.mapFromGlobal(pos) + QPoint(12, 20)
        rect = QRect(local_pos, label.size())
        bounds = host.rect().adjusted(8, 8, -8, -8)
        if bounds.width() > 0 and bounds.height() > 0:
            x = max(bounds.left(), min(rect.x(), bounds.right() - rect.width() + 1))
            y = max(bounds.top(), min(rect.y(), bounds.bottom() - rect.height() + 1))
            rect.moveTo(x, y)

        label.setGeometry(rect)
        label.show()
        label.raise_()

    def hide_tooltip(self):
        if self._label is not None:
            self._label.hide()

    def eventFilter(self, watched, event):
        if watched is self._host and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Leave,
        ):
            self.hide_tooltip()
        return super().eventFilter(watched, event)
