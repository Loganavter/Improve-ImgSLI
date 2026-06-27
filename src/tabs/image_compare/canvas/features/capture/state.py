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
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("capture")
    if isinstance(state, CaptureWidgetState):
        return state
    state = CaptureWidgetState()
    if getattr(view_state, "canvas_widget_state", None) is None:
        view_state.canvas_widget_state = {}
    view_state.canvas_widget_state["capture"] = state
    return state


def replace_capture_widget_state(view_state, state: CaptureWidgetState):
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["capture"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)
