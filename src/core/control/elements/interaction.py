"""In-process pointer delivery at an element's centre (no OS-level injection).

``QTest``/``QApplication.sendEvent`` on the GUI thread, exactly where a real
input event lands. A user right-click is a mouse press/release *and* a
context-menu event, so :func:`click_element` delivers both — a widget that acts
on the mouse path and one that uses ``CustomContextMenu`` behave identically.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtGui import QContextMenuEvent, QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ..discovery import MethodError
from .inventory import Element

#: ``ui_click`` button names → ``Qt.MouseButton``.
_BUTTONS = {
    "left": Qt.MouseButton.LeftButton,
    "right": Qt.MouseButton.RightButton,
    "middle": Qt.MouseButton.MiddleButton,
}


def _send_context_menu(widget: QWidget, pos: QPoint) -> None:
    """Send the context-menu event Qt's platform layer adds to a right-click."""
    try:
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, pos, widget.mapToGlobal(pos)
        )
    except Exception:
        return
    QApplication.sendEvent(widget, event)


def click_element(element: Element, *, button: str = "left", count: int = 1) -> None:
    """Deliver a click to *element* in-process, at its widget-local centre."""
    qt_button = _BUTTONS.get(str(button).lower())
    if qt_button is None:
        raise MethodError(
            f"unknown mouse button {button!r}", "use one of: left, right, middle"
        )
    try:
        clicks = max(1, int(count))
    except (TypeError, ValueError):
        clicks = 1
    widget = element.widget
    pos = element.rect.center()
    if clicks == 2:
        QTest.mouseDClick(widget, qt_button, pos=pos)
        if qt_button == Qt.MouseButton.RightButton:
            _send_context_menu(widget, pos)
        return
    for _ in range(clicks):
        QTest.mouseClick(widget, qt_button, pos=pos)
        if qt_button == Qt.MouseButton.RightButton:
            _send_context_menu(widget, pos)


def hover_element(element: Element) -> None:
    """Move the pointer over *element* and deliver a real enter event."""
    widget = element.widget
    pos = element.rect.center()
    try:
        QTest.mouseMove(widget, pos)
    except Exception:
        pass
    try:
        global_pos = widget.mapToGlobal(pos)
        local = QPointF(pos)
        QApplication.sendEvent(
            widget, QEnterEvent(local, local, QPointF(global_pos))
        )
    except Exception:
        pass


def focus_element(element: Element) -> None:
    """Give keyboard focus to *element*'s widget."""
    try:
        element.widget.setFocus(Qt.FocusReason.OtherFocusReason)
    except Exception as exc:
        raise MethodError(
            f"could not focus {element.id!r}: {exc}",
            "the element may not accept keyboard focus",
        )


def wheel_target(widget, *, raw: bool = False):
    """The widget a wheel over *widget* must be delivered to.

    A wheel over an element means "scroll whatever owns it": the owning
    ``QAbstractScrollArea`` handles the wheel on its VIEWPORT, and an
    interactive child may accept-and-ignore it first (a toolkit Button returns
    without scrolling), so the event is routed to the nearest ancestor scroll
    area's viewport. Two exceptions keep the event where it belongs:
    ``raw=True`` (the caller knows the widget consumes the wheel) and a live
    RHI canvas, which owns its ``Ctrl+wheel`` zoom and must never be routed to
    an ancestor.
    """
    if raw or _is_canvas_widget(widget):
        return widget
    try:
        from PySide6.QtWidgets import QAbstractScrollArea

        area = widget if isinstance(widget, QAbstractScrollArea) else None
        parent = widget.parentWidget() if area is None else None
        while area is None and parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                area = parent
                break
            parent = parent.parentWidget()
        if area is not None:
            return area.viewport() or area
    except Exception:
        return widget
    return widget


def _is_canvas_widget(widget) -> bool:
    """True for a live RHI canvas — it consumes the wheel itself.

    Routing a canvas' wheel to an ancestor scroll area (the default for every
    other element) would steal the ``Ctrl+wheel`` zoom the canvas owns.
    """
    try:
        from PySide6.QtWidgets import QRhiWidget

        return isinstance(widget, QRhiWidget)
    except Exception:
        return False


#: ``ui_wheel`` phase names → Qt scroll phase (the toolkit's glide keys off it).
_WHEEL_PHASES = {
    "none": Qt.ScrollPhase.NoScrollPhase,
    "begin": Qt.ScrollPhase.ScrollBegin,
    "update": Qt.ScrollPhase.ScrollUpdate,
    "end": Qt.ScrollPhase.ScrollEnd,
}


def wheel_element(
    element: Element,
    *,
    delta: int = 120,
    phase: str = "none",
    count: int = 1,
    raw: bool = False,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Deliver wheel events to *element* in-process (one angle-delta step each).

    ``phase`` selects the Qt scroll phase: ``none`` (a plain notch, what a
    discrete mouse wheel sends), ``begin``/``update``/``end`` (what touchpads
    and smooth-scroll compositors send). High-resolution wheels mark every
    event ``begin``, which is the stream that used to starve the scroll glide
    — this verb is how a caller reproduces it without a physical device.
    """
    qt_phase = _WHEEL_PHASES.get(str(phase or "none").lower())
    if qt_phase is None:
        raise MethodError(
            f"unknown wheel phase {phase!r}",
            "use one of: " + ", ".join(sorted(_WHEEL_PHASES)),
        )
    widget = element.widget
    # A wheel over an element means "scroll whatever owns it". The owning
    # QAbstractScrollArea handles the wheel on its VIEWPORT, and an
    # interactive child may accept-and-ignore it first (a toolkit Button with
    # capabilities returns without scrolling), so route to the nearest
    # ancestor scroll area's viewport. ``raw=True`` keeps the event on the
    # element itself (widgets that consume the wheel on purpose).
    widget = wheel_target(widget, raw=raw)
    pos = widget.rect().center()
    global_pos = widget.mapToGlobal(pos)
    angle = QPoint(0, int(delta))
    no_delta = QPoint(0, 0)
    for _ in range(max(1, int(count))):
        event = QWheelEvent(
            QPointF(pos),
            QPointF(global_pos),
            no_delta,
            angle,
            Qt.MouseButton.NoButton,
            modifiers,
            qt_phase,
            False,
        )
        QApplication.sendEvent(widget, event)
