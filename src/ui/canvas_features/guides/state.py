from __future__ import annotations

from dataclasses import dataclass, field, replace

from domain.types import Color

@dataclass
class GuidesWidgetState:
    enabled: bool = False
    thickness: int = 1
    color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    smoothing_enabled: bool = False
    smoothing_interpolation_method: str = "BILINEAR"

    def clone(self) -> "GuidesWidgetState":
        return GuidesWidgetState(
            enabled=bool(self.enabled),
            thickness=int(self.thickness),
            color=self.color,
            smoothing_enabled=bool(self.smoothing_enabled),
            smoothing_interpolation_method=str(self.smoothing_interpolation_method),
        )

def get_guides_widget_state(view_state) -> GuidesWidgetState:
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("guides")
    if isinstance(state, GuidesWidgetState):
        return state
    state = GuidesWidgetState()
    if getattr(view_state, "canvas_widget_state", None) is None:
        view_state.canvas_widget_state = {}
    view_state.canvas_widget_state["guides"] = state
    return state

def replace_guides_widget_state(view_state, state: GuidesWidgetState):
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["guides"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)
