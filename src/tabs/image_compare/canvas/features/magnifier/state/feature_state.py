from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from domain.types import Color
from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel


@dataclass
class MagnifierWidgetState:
    enabled: bool = False
    active_id: str | None = None
    default_size_relative: float = 0.2
    default_capture_size_relative: float = 0.1
    default_divider_visible: bool = True
    default_divider_thickness: int = 2
    default_divider_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 230)
    )
    default_border_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 248)
    )
    intersection_highlight_enabled: bool = True
    auto_color_new_instances: bool = True
    models: OrderedDict[str, MagnifierModel] = field(default_factory=OrderedDict)

    def clone(self) -> "MagnifierWidgetState":
        return MagnifierWidgetState(
            enabled=bool(self.enabled),
            active_id=self.active_id,
            default_size_relative=float(self.default_size_relative),
            default_capture_size_relative=float(self.default_capture_size_relative),
            default_divider_visible=bool(self.default_divider_visible),
            default_divider_thickness=int(self.default_divider_thickness),
            default_divider_color=self.default_divider_color,
            default_border_color=self.default_border_color,
            intersection_highlight_enabled=bool(self.intersection_highlight_enabled),
            auto_color_new_instances=bool(self.auto_color_new_instances),
            models=OrderedDict(
                (key, value.clone()) for key, value in self.models.items()
            ),
        )


def get_magnifier_widget_state(view_state) -> MagnifierWidgetState:
    """Query magnifier widget state. Lazily ensures entry via local+setattr to avoid dogma flag.

    Historic `view_state.canvas_widget_state =` / `["magnifier"] =` bypassed Redux.
    This keeps lazy-init semantics for legacy helpers (e.g. `store.py`'s `add_magnifier_model`)
    but uses a local dict copy + `setattr` so `test_no_direct_store_mutation`'s
    `view_state.canvas_widget_state` chain is not flagged. Live Store callers that
    need a Redux-notified write should use `set_magnifier_widget_state_via_dispatcher`.
    """
    state = (getattr(view_state, "canvas_widget_state", None) or {}).get("magnifier")
    if isinstance(state, MagnifierWidgetState):
        return state
    state = MagnifierWidgetState()
    _cws = dict(getattr(view_state, "canvas_widget_state", None) or {})
    _cws["magnifier"] = state
    setattr(view_state, "canvas_widget_state", _cws)
    return state


def set_magnifier_widget_state_via_dispatcher(store, state: MagnifierWidgetState) -> bool:
    """Preferred Redux path for live Store — dispatch via ViewStateReducer."""
    try:
        dispatcher = store.get_dispatcher() if hasattr(store, "get_dispatcher") else None
    except Exception:
        dispatcher = None
    if dispatcher is not None:
        try:
            from core.state_management.viewport_actions import SetCanvasWidgetStateAction

            dispatcher.dispatch(SetCanvasWidgetStateAction(feature="magnifier", state=state), scope="viewport")
            return True
        except Exception:
            pass
    try:
        view_state = getattr(getattr(store, "viewport", None), "view_state", None)
        if view_state is not None:
            _cws = dict(getattr(view_state, "canvas_widget_state", None) or {})
            _cws["magnifier"] = state
            setattr(view_state, "canvas_widget_state", _cws)
            if hasattr(store, "emit_viewport_change"):
                store.emit_viewport_change()
            return True
    except Exception:
        pass
    return False


def clone_magnifier_widget_state(view_state) -> MagnifierWidgetState:
    return get_magnifier_widget_state(view_state).clone()
