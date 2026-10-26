"""``IMGSLI_SPLIT_TRACE``-gated per-frame correlation trace for the split line.

Question this answers (one grep, no debugger): *in the frame the user is
looking at, did the base-image pass and the ``DividerPass`` line get the same
split, where did each put it, and did they land in the same QRhi frame slot?*
Both passes read one ``SceneFrame.split_position_visual``, so a visible "the
line is a frame off from the seam" can only come from (a) the two consumers
being handed different values, (b) geometry disagreeing (letterbox vs
view-mapped content rect), or (c) a uniform write landing in a different
frame-in-flight slot (see
``docs/dev/rendering/investigations/multitile-uniform-desync.md``).

The trace prints one line per consumer per frame with a shared ``frame=N`` id,
plus ``slot=`` (``QRhi.currentFrameSlot()``) and ``presents=`` (the widget's
present counter), so the log can be tied to the frame the user actually saw.
When the camera is neutral (zoom 1, no pan) the divider line also carries
``expected=``/``delta=`` against the base pass's own letterbox mapping, and a
``MISMATCH`` marker when they disagree by more than a pixel and a half --
that is the exact failure the user reports, so it announces itself.

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
#: widget id -> (frame id, base-pass record) for the divider's position check.
#: Per widget on purpose: the live canvas and the export/preview canvas emit
#: base frames into the same stream, and a global frame->record map loses the
#: live record to pruning as soon as the exporter paints (measured: 7 of 141
#: divider frames kept their check).
_BASE: dict[int, tuple[int, dict]] = {}


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


def _present_state(widget) -> tuple[int, int]:
    """(QRhi frame-in-flight slot, presents completed) for this widget.

    ``slot`` decides whether a write lands in the copy the GPU is about to
    read; ``presents`` is the widget's own counter, so a log line can be tied
    to a frame the user actually saw.
    """
    slot = -1
    try:
        rhi = widget.rhi()
        if rhi is not None:
            slot = int(rhi.currentFrameSlot())
    except Exception:
        slot = -1
    try:
        presents = int(getattr(widget, "_rhi_presents_completed", -1))
    except Exception:
        presents = -1
    return slot, presents


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
    canvas_width: float,
    canvas_height: float,
) -> int:
    """Open a frame id and log what the base-image pass is about to draw.

    Called once per built render context (i.e. once per frame per canvas).
    Returns the frame id the later overlay traces of this frame reuse.
    """
    frame = _new_frame(widget)
    if not split_trace_enabled():
        return frame
    display_split, zoom, pan_x, pan_y = _camera(widget)
    slot, presents = _present_state(widget)
    _BASE[id(widget)] = (
        frame,
        {
        "split": float(split),
        "lb1": tuple(float(v) for v in letterbox1),
        "zoom": zoom,
        "pan": (pan_x, pan_y),
        "canvas_w": float(canvas_width),
        "width": float(canvas_width),
        },
    )
    logger.info(
        "%s frame=%d phase=base widget=%#x mode=%s slot=%d presents=%d "
        "split=%.6f scene_visual=%.6f scene_split=%.6f override=%r "
        "inner_rect=%r content_rect=%r view_split=%r view_split_visual=%r "
        "display=%.6f zoom=%.4f pan=(%.2f,%.2f) canvas=(%.0fx%.0f) lb1=%r",
        _TAG,
        frame,
        id(widget),
        mode,
        slot,
        presents,
        float(split),
        float(getattr(scene_frame, "split_position_visual", -1.0)),
        float(getattr(render_scene, "split_position_visual", -1.0)),
        getattr(scene_frame, "split_override", None),
        getattr(state, "_inner_content_rect_px", None),
        getattr(state, "_content_rect_px", None),
        getattr(view_state, "split_position", None),
        getattr(view_state, "split_position_visual", None),
        float(display_split),
        float(zoom),
        float(pan_x),
        float(pan_y),
        float(canvas_width),
        float(canvas_height),
        tuple(float(v) for v in letterbox1),
    )
    return frame


def trace_divider_frame(
    widget,
    spec,
    *,
    canvas_width: float = 0.0,
    canvas_height: float = 0.0,
) -> None:
    """Log where ``DividerPass`` puts the line for the current frame.

    ``spec`` is the resolved ``overlay_model.DividerSpec`` of this frame --
    the caller resolves it, so the line the log describes is the line the
    pass draws (same object, same frame id the base pass opened). With a
    neutral camera the position is also checked against the base pass's own
    letterbox mapping: a disagreement is the reported "line sits one frame
    off" symptom, printed as ``MISMATCH``.
    """
    if not split_trace_enabled():
        return
    frame = current_frame_id(widget)
    _display, zoom, pan_x, pan_y = _camera(widget)
    slot, presents = _present_state(widget)
    recorded = _BASE.get(id(widget))
    base = recorded[1] if recorded is not None and recorded[0] == frame else {}

    extra = " expected=n/a delta=n/a"
    mismatch = ""
    lb1 = base.get("lb1") or ()
    if len(lb1) == 4 and float(base.get("zoom", 1.0)) == 1.0 and abs(
        float(base.get("pan", (0.0, 0.0))[0])
    ) < 1e-6 and abs(float(base.get("pan", (0.0, 0.0))[1])) < 1e-6:
        width = float(base.get("canvas_w") or canvas_width)
        if width > 0:
            expected = (lb1[0] + lb1[2] * float(base.get("split", 0.0))) * width
            delta = float(spec.position_px) - expected
            extra = " expected=%.2f delta=%+.2f" % (expected, delta)
            if abs(delta) > 1.5:
                mismatch = " MISMATCH"

    logger.info(
        "%s frame=%d phase=divider widget=%#x slot=%d presents=%d "
        "split=%.6f pos=%.2f thickness=%.2f horizontal=%s "
        "clip=(%.2f,%.2f,%.2f,%.2f) canvas=(%.0fx%.0f) zoom=%.4f "
        "pan=(%.2f,%.2f) show=%s%s%s",
        _TAG,
        frame,
        id(widget),
        slot,
        presents,
        float(base.get("split", 0.0)),
        float(spec.position_px),
        float(spec.thickness_px),
        bool(spec.is_horizontal),
        float(spec.clip_x),
        float(spec.clip_y),
        float(spec.clip_w),
        float(spec.clip_h),
        float(canvas_width),
        float(canvas_height),
        float(zoom),
        float(pan_x),
        float(pan_y),
        bool(spec.show),
        extra,
        mismatch,
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
