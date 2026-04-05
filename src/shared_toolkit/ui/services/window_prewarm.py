from __future__ import annotations
from typing import Protocol, runtime_checkable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

@runtime_checkable
class OffscreenPrewarmAware(Protocol):
    def begin_offscreen_prewarm(self) -> None: ...
    def end_offscreen_prewarm(self) -> None: ...

def prewarm_widget_window(
    app: QApplication,
    widget: QWidget,
    *,
    name: str | None = None,
) -> None:
    aware = widget if isinstance(widget, OffscreenPrewarmAware) else None
    if aware is not None:
        aware.begin_offscreen_prewarm()

    widget.ensurePolished()
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    try:
        widget.show()
        app.processEvents()
        widget.repaint()
        app.processEvents()
        widget.hide()
    finally:
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        if aware is not None:
            aware.end_offscreen_prewarm()

def prewarm_widget_window_once(
    app: QApplication,
    widget: QWidget,
    *,
    name: str | None = None,
) -> bool:
    if bool(widget.property("_offscreen_prewarmed")):
        return False
    prewarm_widget_window(app, widget, name=name)
    widget.setProperty("_offscreen_prewarmed", True)
    return True
