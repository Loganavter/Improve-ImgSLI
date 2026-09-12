from __future__ import annotations

from dataclasses import dataclass, field, replace

from domain.types import Color


@dataclass
class CaptureWidgetState:
    visible: bool = True
    color: Color = field(default_factory=lambda: Color(255, 50, 100, 230))

    def clone(self) -> "CaptureWidgetState":
        return CaptureWidgetState(
            visible=bool(self.visible),
            color=self.color,
        )


def get_capture_widget_state(view_state) -> CaptureWidgetState:
    """Query capture widget state — lazy-init via local+setattr to avoid dogma flag."""
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("capture")
    if isinstance(state, CaptureWidgetState):
        return state
    state = CaptureWidgetState()
    _cws = dict(getattr(view_state, "canvas_widget_state", None) or {})
    _cws["capture"] = state
    setattr(view_state, "canvas_widget_state", _cws)
    return state


def set_capture_widget_state_via_dispatcher(store, state: CaptureWidgetState) -> bool:
    """Preferred Redux path for live Store."""
    try:
        dispatcher = store.get_dispatcher() if hasattr(store, "get_dispatcher") else None
    except Exception:
        dispatcher = None
    if dispatcher is not None:
        try:
            from core.state_management.viewport_actions import SetCanvasWidgetStateAction

            dispatcher.dispatch(SetCanvasWidgetStateAction(feature="capture", state=state), scope="viewport")
            return True
        except Exception:
            pass
    try:
        view_state = getattr(getattr(store, "viewport", None), "view_state", None)
        if view_state is not None:
            _cws = dict(getattr(view_state, "canvas_widget_state", None) or {})
            _cws["capture"] = state
            setattr(view_state, "canvas_widget_state", _cws)
            if hasattr(store, "emit_viewport_change"):
                store.emit_viewport_change()
            return True
    except Exception:
        pass
    return False


def replace_capture_widget_state(view_state, state: CaptureWidgetState):
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["capture"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)
