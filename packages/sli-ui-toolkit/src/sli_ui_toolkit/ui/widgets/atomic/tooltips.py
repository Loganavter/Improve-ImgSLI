from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from ..helpers import draw_rounded_shadow

class _TooltipBubble(QWidget):
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 5

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
            self.SHADOW_RADIUS,
        )
        layout.setSpacing(0)
        self.label = QLabel(self)
        self.label.setObjectName("TooltipContentWidget")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label)
        self.hide()

    def set_text(self, text: str):
        self.label.setText(text)
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

class _TooltipInterceptor(QObject):
    def eventFilter(self, watched, event):
        if not _should_handle_tooltip_widget(watched):
            return super().eventFilter(watched, event)
        tooltip_text = watched.toolTip()

        if event.type() == QEvent.Type.ToolTip:
            global_pos = (
                event.globalPos()
                if hasattr(event, "globalPos")
                else watched.mapToGlobal(watched.rect().center())
            )
            PathTooltip.get_instance().show_tooltip(global_pos, tooltip_text)
            return True

        if event.type() in (
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
        ):
            PathTooltip.get_instance().hide_tooltip()
        return super().eventFilter(watched, event)

class _ApplicationTooltipInterceptor(QObject):
    def eventFilter(self, watched, event):
        if not _should_handle_tooltip_widget(watched):
            return super().eventFilter(watched, event)

        tooltip_text = watched.toolTip()
        if event.type() == QEvent.Type.ToolTip:
            global_pos = (
                event.globalPos()
                if hasattr(event, "globalPos")
                else watched.mapToGlobal(watched.rect().center())
            )
            PathTooltip.get_instance().show_tooltip(global_pos, tooltip_text)
            return True

        if event.type() in (
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.FocusOut,
            QEvent.Type.WindowDeactivate,
        ):
            PathTooltip.get_instance().hide_tooltip()
        return super().eventFilter(watched, event)

def _should_handle_tooltip_widget(watched) -> bool:
    if not isinstance(watched, QWidget):
        return False
    if bool(getattr(watched, "_disable_custom_tooltip", False)):
        return False
    if not hasattr(watched, "toolTip"):
        return False
    return bool(watched.toolTip())

def install_custom_tooltip(widget: QWidget):
    if widget is None or getattr(widget, "_custom_tooltip_installed", False):
        return
    interceptor = _TooltipInterceptor(widget)
    widget.installEventFilter(interceptor)
    widget._custom_tooltip_installed = True
    widget._custom_tooltip_interceptor = interceptor

def install_application_tooltips(app: QApplication | None):
    if app is None or getattr(app, "_custom_tooltip_installed", False):
        return
    interceptor = _ApplicationTooltipInterceptor(app)
    app.installEventFilter(interceptor)
    app._custom_tooltip_installed = True
    app._custom_tooltip_interceptor = interceptor

def set_application_tooltips_enabled(enabled: bool) -> None:
    PathTooltip.get_instance().set_enabled(enabled)

def application_tooltips_enabled() -> bool:
    return PathTooltip.get_instance().is_enabled()

class PathTooltip(QObject):
    _instance = None
    DEFAULT_SHOW_DELAY_MS = 500

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PathTooltip()
        return cls._instance

    def __init__(self):
        if PathTooltip._instance is not None:
            raise RuntimeError("Singleton")
        super().__init__(None)
        self._label: _TooltipBubble | None = None
        self._host: QWidget | None = None
        self._enabled = True
        self._show_delay_ms = self.DEFAULT_SHOW_DELAY_MS
        self._pending_pos: QPoint | None = None
        self._pending_text: str = ""
        self._pending_delay_ms = 0
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_pending_tooltip)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)

    def _is_alive(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        try:
            widget.objectName()
            return True
        except RuntimeError:
            return False

    def _clear_label_ref(self):
        self._label = None
        self._host = None

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
        return widget.window()

    def _ensure_label(self, host: QWidget) -> _TooltipBubble:
        if not self._is_alive(self._label):
            self._label = None
        if not self._is_alive(self._host):
            self._host = None

        if self._label is not None and self._host is host:
            return self._label

        if self._host is not None:
            try:
                self._host.removeEventFilter(self)
            except Exception:
                pass

        if self._label is None:
            self._label = _TooltipBubble(host)
            self._label.destroyed.connect(lambda *_: self._clear_label_ref())
            self._label.hide()
        else:
            self._label.setParent(host)

        self._host = host
        self._host.installEventFilter(self)
        self._apply_style()
        return self._label

    def _apply_style(self):
        if not self._is_alive(self._label):
            self._label = None
            return
        self._label.label.style().unpolish(self._label.label)
        self._label.label.style().polish(self._label.label)
        self._label.label.update()
        self._label.update()

    def _show_now(self, pos: QPoint, text: str) -> None:
        if not self._enabled:
            return
        if not text:
            return

        host = self._resolve_host(pos)
        if host is None:
            return

        label = self._ensure_label(host)
        label.set_text(text)

        local_pos = host.mapFromGlobal(pos) + QPoint(0, 20)
        rect = QRect(local_pos, label.size())
        bounds = host.rect().adjusted(8, 8, -8, -8)
        if bounds.width() > 0 and bounds.height() > 0:
            x = max(bounds.left(), min(rect.x(), bounds.right() - rect.width() + 1))
            y = max(bounds.top(), min(rect.y(), bounds.bottom() - rect.height() + 1))
            rect.moveTo(x, y)

        label.setGeometry(rect)
        label.show()
        label.raise_()

    def _show_pending_tooltip(self) -> None:
        pos = self._pending_pos
        text = self._pending_text
        self._pending_pos = None
        self._pending_text = ""
        self._pending_delay_ms = 0
        if pos is None or not text:
            return
        self._show_now(pos, text)

    def show_tooltip(self, pos: QPoint, text: str, delay_ms: int | None = None):
        if not self._enabled:
            return
        if not text:
            return

        delay = self._show_delay_ms if delay_ms is None else max(0, int(delay_ms))
        self._pending_pos = QPoint(pos)
        self._pending_text = str(text)
        self._pending_delay_ms = delay

        if delay <= 0:
            self._show_timer.stop()
            self._show_pending_tooltip()
            return

        self._show_timer.start(delay)

    def hide_tooltip(self):
        self._show_timer.stop()
        self._pending_pos = None
        self._pending_text = ""
        self._pending_delay_ms = 0
        if self._is_alive(self._label):
            self._label.hide()
        else:
            self._label = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self.hide_tooltip()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_show_delay_ms(self, delay_ms: int) -> None:
        self._show_delay_ms = max(0, int(delay_ms))

    def show_delay_ms(self) -> int:
        return int(self._show_delay_ms)

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
