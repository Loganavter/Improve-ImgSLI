"""``IMGSLI_SPLIT_TRACE``-gated per-frame correlation trace for the split line.

Question this answers (one grep, no debugger): *in the frame the user is
looking at, did the base-image pass and the ``DividerPass`` line get the same
split, and where did each put it?* Both passes read one
``SceneFrame.split_position_visual``, so a visible "line is one frame off from
the seam" can only come from either (a) the two consumers being handed
different values, or (b) a uniform write landing in a different
frame-in-flight slot (see
``docs/dev/rendering/investigations/multitile-uniform-desync.md``). The trace
prints one line per consumer per frame with a shared ``frame=N`` id, so the
pair can be read off ``log.txt`` directly.

Env flag (either spelling, see ``shared/debug_flags``):

    BLINKTABLE_SPLIT_TRACE=1
    IMGSLI_SPLIT_TRACE=1        (legacy spelling, same flag)

Nothing is logged (and nothing is computed) when the flag is off; the calls
sit on the two per-frame hot paths, so every entry point returns immediately.
"""

from __future__ import annotations

import itertools
import logging

from core.log_names import APP_LOGGER_NAME
from shared.debug_flags import env_flag

__all__ = [
    "current_frame_id",
    "split_trace_enabled",
    "trace_base_frame",
    "trace_divider_frame",
    "trace_split_dispatch",
]

logger = logging.getLogger(f"{APP_LOGGER_NAME}.split_trace")

_TAG = "[split-trace]"
#: Monotonic frame id shared by every consumer of one frame.
_FRAME_IDS = itertools.count(1)
#: widget id -> the frame id its base pass opened (the frame's owner).
_CURRENT: dict[int, int] = {}


def split_trace_enabled() -> bool:
    """True when ``*_SPLIT_TRACE`` is set (checked per call, env-cheap)."""
    return env_flag("IMGSLI_SPLIT_TRACE")


def current_frame_id(widget) -> int:
    """Frame id opened by this widget's base pass, or 0 before its first frame."""
    return int(_CURRENT.get(id(widget), 0))


def _new_frame(widget) -> int:
    frame = next(_FRAME_IDS)
    _CURRENT[id(widget)] = frame
    return frame


def _camera(widget) -> tuple[float, float, float, float]:
    """(display_split, zoom, pan_x, pan_y) read live from the widget's viewport."""
    from ui.canvas_infra.viewport.state import (
        get_display_split_position,
        get_pan_offset_x,
        get_pan_offset_y,
        get_zoom_level,
    )

    return (
        float(get_display_split_position(widget)),
        float(get_zoom_level(widget)),
        float(get_pan_offset_x(widget)),
        float(get_pan_offset_y(widget)),
    )


def trace_base_frame(
    widget,
    *,
    mode: str,
    split: float,
    scene_frame,
    render_scene,
    view_state,
    state,
    letterbox1,
) -> int:
    """Open a frame id and log what the base-image pass is about to draw.

    Called once per built render context (i.e. once per frame per canvas).
    Returns the frame id the later overlay traces of this frame reuse.
    """
    frame = _new_frame(widget)
    if not split_trace_enabled():
        return frame
    display_split, zoom, pan_x, pan_y = _camera(widget)
    inner_rect = getattr(state, "_inner_content_rect_px", None)
    content_rect = getattr(state, "_content_rect_px", None)
    logger.info(
        "%s frame=%d phase=base widget=%#x mode=%s split=%.6f "
        "scene_visual=%.6f scene_split=%.6f override=%r inner_rect=%r "
        "content_rect=%r view_split=%r view_split_visual=%r display=%.6f "
        "zoom=%.4f pan=(%.2f,%.2f) lb1=%r",
        _TAG,
        frame,
        id(widget),
        mode,
        float(split),
        float(getattr(scene_frame, "split_position_visual", -1.0)),
        float(getattr(render_scene, "split_position_visual", -1.0)),
        getattr(scene_frame, "split_override", None),
        inner_rect,
        content_rect,
        getattr(view_state, "split_position", None),
        getattr(view_state, "split_position_visual", None),
        float(display_split),
        float(zoom),
        pan_x,
        pan_y,
        tuple(letterbox1),
    )
    return frame


def trace_divider_frame(widget, spec) -> None:
    """Log where ``DividerPass`` puts the line for the current frame.

    ``spec`` is the resolved ``overlay_model.DividerSpec`` of this frame --
    the caller resolves it, so the line the log describes is the line the
    pass draws (same object, same frame id the base pass opened).
    """
    if not split_trace_enabled():
        return
    _display, zoom, pan_x, pan_y = _camera(widget)
    split = 0.0
    if spec.clip_w > 0 and not spec.is_horizontal:
        split = (spec.position_px - spec.clip_x) / spec.clip_w
    elif spec.clip_h > 0:
        split = (spec.position_px - spec.clip_y) / spec.clip_h
    logger.info(
        "%s frame=%d phase=divider widget=%#x split=%.6f pos=%.2f "
        "thickness=%.2f horizontal=%s clip=(%.2f,%.2f,%.2f,%.2f) "
        "zoom=%.4f pan=(%.2f,%.2f) show=%s",
        _TAG,
        current_frame_id(widget),
        id(widget),
        float(split),
        float(spec.position_px),
        float(spec.thickness_px),
        bool(spec.is_horizontal),
        float(spec.clip_x),
        float(spec.clip_y),
        float(spec.clip_w),
        float(spec.clip_h),
        float(zoom),
        pan_x,
        pan_y,
        bool(spec.show),
    )


def trace_split_dispatch(
    source: str,
    *,
    split: float,
    dragging: bool,
    visual_sent: bool,
) -> None:
    """Log one drag/sync dispatch: which actions actually reached the store.

    ``visual_sent=False`` while ``dragging=False`` is the tell that the frame
    will keep rendering the previous ``split_position_visual``.
    """
    if not split_trace_enabled():
        return
    logger.info(
        "%s phase=dispatch source=%s split=%.6f dragging=%s visual_sent=%s",
        _TAG,
        source,
        float(split),
        bool(dragging),
        bool(visual_sent),
    )
