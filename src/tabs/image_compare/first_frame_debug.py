"""Image Compare first-frame timeline (thin wrapper).

See ``shared/rendering/first_frame_debug.py`` for the shared
implementation; this module binds it to Image Compare's env gate
(``IMGSLI_IC_FIRST_FRAME_DEBUG``), log tag and renderer attributes so both
canvas tabs share one code path while keeping their own env flags and
timeline state.
"""

from __future__ import annotations

from shared.rendering.first_frame_debug import FirstFrameDebug

_ffd = FirstFrameDebug(
    env_name="IMGSLI_IC_FIRST_FRAME_DEBUG",
    log_tag="ic-first-frame",
    attr_prefix="_ic_first_frame_debug",
    renderer_attr="_rhi_renderer",
    composition_attr="_active_render_plan",
)

ic_first_frame_debug_enabled = _ffd.enabled
ic_first_frame_debug = _ffd.debug
ic_first_frame_readiness = _ffd.readiness
ic_first_frame_readiness_repr = _ffd.readiness_repr
ic_first_frame_surface_repr = _ffd.surface_repr

__all__ = [
    "ic_first_frame_debug_enabled",
    "ic_first_frame_debug",
    "ic_first_frame_readiness",
    "ic_first_frame_readiness_repr",
    "ic_first_frame_surface_repr",
]
