from __future__ import annotations

def letterbox_params(host) -> tuple[float, float, float, float] | None:
    state = getattr(host, "runtime_state", None)
    params = getattr(state, "_letterbox_params", None) if state is not None else None
    if not params:
        return None
    try:
        lb = params[0]
    except (IndexError, TypeError):
        return None
    if lb is None or len(lb) < 4:
        return None
    ox, oy, sx, sy = (float(lb[0]), float(lb[1]), float(lb[2]), float(lb[3]))
    if sx <= 0.0 or sy <= 0.0:
        return None
    return ox, oy, sx, sy

def capture_letterbox_focus(host) -> tuple[float, float] | None:
    """Return the image sample coordinate under the viewport center."""
    lb = letterbox_params(host)
    if lb is None:
        return None

    from .state import get_pan_offset_x, get_pan_offset_y

    ox, oy, sx, sy = lb
    raw_x = 0.5 - float(get_pan_offset_x(host) or 0.0)
    raw_y = 0.5 - float(get_pan_offset_y(host) or 0.0)
    return ((raw_x - ox) / sx, (raw_y - oy) / sy)

def restore_letterbox_focus(host, focus: tuple[float, float] | None) -> bool:
    if focus is None:
        return False
    lb = letterbox_params(host)
    if lb is None:
        return False

    from .state import get_zoom_level, set_pan_offsets

    if float(get_zoom_level(host) or 1.0) <= 1.0:
        set_pan_offsets(host, 0.0, 0.0)
        return True

    ox, oy, sx, sy = lb
    sample_x, sample_y = focus
    new_pan_x = 0.5 - (ox + (float(sample_x) * sx))
    new_pan_y = 0.5 - (oy + (float(sample_y) * sy))
    set_pan_offsets(host, new_pan_x, new_pan_y)
    return True
