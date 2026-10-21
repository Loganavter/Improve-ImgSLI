"""Shared value helpers + coordinate-space vocabulary for canvas scenes."""

from __future__ import annotations

from typing import Any

#: Spaces a geometry field may declare (R4). ``None`` means "not applicable".
SPACE_CANVAS_PX = "canvas_px"
SPACE_COMPOSITION_PX = "composition_px"
SPACE_WIDGET_PX = "widget_px"
SPACE_FRAMEBUFFER_PX = "framebuffer_px"
SPACE_RELATIVE = "relative"

#: ``DividerWidgetState`` defaults — what the divider feature paints before its
#: state is first materialized (``features/divider/state/feature_state.py``).
_IC_DEFAULT_DIVIDER_VISIBLE = True
_IC_DEFAULT_DIVIDER_THICKNESS = 3



# ---------------------------------------------------------------------------
# shared value helpers
# ---------------------------------------------------------------------------


def _num(value: Any, default: float = 0.0) -> float:
    """A JSON-safe float; ``-0.0`` is normalized so two reads stay identical."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    if out != out:  # NaN: never emit it, the payload must stay valid JSON
        out = float(default)
    return 0.0 if out == 0.0 else out


def _point_or_none(point: Any) -> list[float] | None:
    if point is None:
        return None
    return [_num(getattr(point, "x", 0.0)), _num(getattr(point, "y", 0.0))]


def _stored_canvas_widget_state(view_state: Any, key: str) -> tuple[Any, bool]:
    """Read ``canvas_widget_state[key]`` **without** lazily creating it (R2)."""
    cws = getattr(view_state, "canvas_widget_state", None) or {}
    try:
        state = cws.get(key)
    except Exception:
        state = None
    return state, state is not None


