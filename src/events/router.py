from __future__ import annotations

import logging
import os

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from tabs.registry import get_shared_tab_registry

# dnd-override/kbd-route trace lines fire on every mouse/key event once
# --debug is on, drowning out other subsystems' debug output (e.g.
# IMGSLI_RESIZE_DEBUG render tracing). Gated on its own opt-in flag, off by
# default even under --debug -- same convention as
# shared/rendering/render_debug.py's IMGSLI_RESIZE_DEBUG.
logger = logging.getLogger("ImproveImgSLI.nav")
if os.environ.get("UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)

def _belongs_to_canvas(event_handler, watched_obj) -> bool:
    tab = get_shared_tab_registry().get_active_tab()
    if tab is None:
        return False
    if not tab.consumes_canvas_key_events():
        return False
    return tab.owns_widget(watched_obj)

def route_drag_and_drop_override(event_handler, event: QEvent, dnd_service) -> bool:
    event_type = event.type()

    from events.image_carry import ImageCarryService

    carry = ImageCarryService._instance
    if carry is not None and carry.is_active():
        if event_type == QEvent.Type.MouseMove:
            carry.update_position(event)
            logger.debug("[dnd-override] carry=active MouseMove -> update_position")
            return True
        if event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                carry.finish(event)
                logger.debug("[dnd-override] carry=active LeftRelease -> finish")
                return True
            if event.button() == Qt.MouseButton.RightButton:
                carry.cancel()
                logger.debug("[dnd-override] carry=active RightRelease -> cancel")
                return True
        if (
            event_type == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            carry.cancel()
            logger.debug("[dnd-override] carry=active Escape -> cancel")
            return True
        if event_type in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Enter,
            QEvent.Type.Leave,
        ):
            logger.debug("[dnd-override] carry=active %s -> swallow", event_type.name)
            return True

    if not dnd_service.is_dragging():
        return False
    if event_type == QEvent.Type.MouseMove:
        dnd_service.update_drag_position(event)
        logger.debug("[dnd-override] dnd=dragging MouseMove -> update_drag_position")
        return True
    if event_type == QEvent.Type.MouseButtonRelease:
        dnd_service.finish_drag(event)
        logger.debug("[dnd-override] dnd=dragging Release -> finish_drag")
        return True
    if (
        event_type == QEvent.Type.KeyPress
        and isinstance(event, QKeyEvent)
        and event.key() == Qt.Key.Key_Escape
    ):
        dnd_service.cancel_drag()
        logger.debug("[dnd-override] dnd=dragging Escape -> cancel_drag")
        return True
    if event_type in (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.Enter,
        QEvent.Type.Leave,
    ):
        logger.debug("[dnd-override] dnd=dragging %s -> swallow", event_type.name)
        return True
    return False

def route_global_keyboard_event(event_handler, watched_obj, event: QEvent) -> bool:
    event_type = event.type()
    if event_type not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        return False
    if _belongs_to_canvas(event_handler, watched_obj):
        if event_type == QEvent.Type.KeyPress:
            event_handler.canvas_keyboard_press_event_signal.emit(event)
        else:
            event_handler.canvas_keyboard_release_event_signal.emit(event)
        logger.debug(
            "[kbd-route] %s -> CANVAS (watched=%s owns_widget=True)",
            "Press" if event_type == QEvent.Type.KeyPress else "Release",
            type(watched_obj).__name__,
        )
        return True
    if not event_handler.keyboard_handler.should_route_globally(event, watched_obj):
        logger.debug(
            "[kbd-route] %s -> CONSUMED_BY_TAB (watched=%s should_route_globally=False)",
            "Press" if event_type == QEvent.Type.KeyPress else "Release",
            type(watched_obj).__name__,
        )
        return False
    if event_type == QEvent.Type.KeyPress:
        event_handler.global_keyboard_press_event_signal.emit(event)
    else:
        event_handler.global_keyboard_release_event_signal.emit(event)
    logger.debug(
        "[kbd-route] %s -> GLOBAL (watched=%s key=%s)",
        "Press" if event_type == QEvent.Type.KeyPress else "Release",
        type(watched_obj).__name__,
        event.key() if isinstance(event, QKeyEvent) else "?",
    )
    return True