from __future__ import annotations

from dataclasses import dataclass, field, replace

from domain.types import Color


@dataclass
class DividerWidgetState:
    visible: bool = True
    color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    thickness: int = 3

    def clone(self) -> "DividerWidgetState":
        return DividerWidgetState(
            visible=bool(self.visible),
            color=self.color,
            thickness=int(self.thickness),
        )


def get_divider_widget_state(view_state) -> DividerWidgetState:
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("divider")
    if isinstance(state, DividerWidgetState):
        return state
    state = DividerWidgetState()
    if getattr(view_state, "canvas_widget_state", None) is None:
        view_state.canvas_widget_state = {}
    view_state.canvas_widget_state["divider"] = state
    return state


def replace_divider_widget_state(view_state, state: DividerWidgetState):
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["divider"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)
