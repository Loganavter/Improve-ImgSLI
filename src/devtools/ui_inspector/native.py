"""App-side native-window diagnostics (kept out of the toolkit — QRhiWidget
is app-side canvas infrastructure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from PySide6.QtWidgets import QRhiWidget


@dataclass(slots=True)
class NativeWindowInfo:
    class_name: str
    object_name: str
    is_top_level: bool
    has_native_window: bool
    wa_native_window: bool
    wa_paint_on_screen: bool
    is_qrhiwidget: bool
    sibling_qrhiwidgets: tuple[str, ...]

    @property
    def selector(self) -> str:
        if self.object_name:
            return f"{self.class_name}#{self.object_name}"
        return self.class_name


def window_has_qrhiwidget(widget: QWidget) -> bool:
    top = widget.window()
    if top is None:
        return False
    if isinstance(top, QRhiWidget):
        return True
    return bool(top.findChildren(QRhiWidget))


def native_chain(widget: QWidget) -> Iterable[NativeWindowInfo]:
    current: QWidget | None = widget
    top = widget.window()
    while current is not None:
        yield NativeWindowInfo(
            class_name=type(current).__name__,
            object_name=current.objectName(),
            is_top_level=current is top,
            has_native_window=current.internalWinId() != 0,
            wa_native_window=current.testAttribute(Qt.WidgetAttribute.WA_NativeWindow),
            wa_paint_on_screen=current.testAttribute(
                Qt.WidgetAttribute.WA_PaintOnScreen
            ),
            is_qrhiwidget=isinstance(current, QRhiWidget),
            sibling_qrhiwidgets=_sibling_qrhiwidgets(current),
        )
        current = current.parentWidget()


def _sibling_qrhiwidgets(widget: QWidget) -> tuple[str, ...]:
    parent = widget.parentWidget()
    if parent is None:
        return ()
    out: list[str] = []
    for sibling in parent.findChildren(
        QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
    ):
        if sibling is widget:
            continue
        if isinstance(sibling, QRhiWidget):
            out.append(type(sibling).__name__)
    return tuple(out)
