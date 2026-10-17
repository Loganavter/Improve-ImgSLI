"""Context-menu slot routing for the image_compare canvas widget.

Bodies moved verbatim out of ``canvas/widget.py`` (CODE_PATTERNS thin owner +
``use_cases`` module, Part D split). Plain functions taking the widget as
their first argument; the Qt-required ``contextMenuEvent`` override and its
two private helpers stay same-named one-line delegators on ``CanvasWidget``.
"""

from __future__ import annotations

from PySide6.QtGui import QContextMenuEvent

from ui.context_menu.manager import open_context_menu
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


def context_menu_event(widget, event: QContextMenuEvent) -> None:
    """Body of ``CanvasWidget.contextMenuEvent``."""
    from ui.canvas_infra.scene.context_menu_zones import (
        ContextMenuHitContext,
        is_context_menu_suppressed,
    )

    session_type = widget._active_session_type()
    if session_type is None:
        event.ignore()
        return
    store = getattr(widget.runtime_state, "_store", None)
    # Space+RMB is the single-image preview gesture — the host menu must
    # not open on top of it.
    if store is not None and bool(store.viewport.interaction_state.space_bar_pressed):
        event.accept()
        return
    if store is not None and is_context_menu_suppressed(
        ContextMenuHitContext(
            store=store,
            canvas=widget,
            local_pos=event.pos(),
            session_type=session_type,
        )
    ):
        event.accept()
        return
    slot = widget._context_menu_slot_at(event.pos())
    if slot is None:
        event.ignore()
        return
    menu = open_context_menu(
        ContextMenuRequest(
            source_widget=widget,
            global_pos=event.globalPos(),
            local_pos=event.pos(),
            session_type=session_type,
            target=ContextMenuTarget(kind=f"{session_type}_slot", id=slot),
        )
    )
    if menu is None:
        event.ignore()
        return
    event.accept()


def active_session_type(widget) -> str | None:
    store = getattr(widget.runtime_state, "_store", None)
    if store is None:
        return None
    try:
        session = store.get_active_workspace_session()
    except Exception:
        return None
    return session.session_type if session is not None else None


def context_menu_slot_at(widget, pos):
    store = getattr(widget.runtime_state, "_store", None)
    if store is None:
        return None
    view = store.viewport.view_state
    split = float(
        getattr(
            view,
            "split_position_visual",
            getattr(widget, "split_position", 0.5),
        )
    )
    split = max(0.0, min(1.0, split))
    if bool(getattr(view, "is_horizontal", getattr(widget, "is_horizontal", False))):
        return 1 if pos.y() <= widget.height() * split else 2
    return 1 if pos.x() <= widget.width() * split else 2
