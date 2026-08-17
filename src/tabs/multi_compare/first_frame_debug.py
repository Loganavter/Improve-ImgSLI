"""Multi Compare first-frame timeline (thin wrapper).

See ``shared/rendering/first_frame_debug.py`` for the shared
implementation; this module binds it to Multi Compare's env gate
(``IMGSLI_MC_FIRST_FRAME_DEBUG``), log tag and renderer attributes so both
canvas tabs share one code path while keeping their own env flags and
timeline state.
"""

from __future__ import annotations

from shared.rendering.first_frame_debug import FirstFrameDebug

_ffd = FirstFrameDebug(
    env_name="IMGSLI_MC_FIRST_FRAME_DEBUG",
    log_tag="mc-first-frame",
    attr_prefix="_mc_first_frame_debug",
    renderer_attr="_renderer",
    composition_attr="_active_composition",
)

mc_first_frame_debug_enabled = _ffd.enabled
mc_first_frame_debug = _ffd.debug
mc_first_frame_readiness = _ffd.readiness
mc_first_frame_readiness_repr = _ffd.readiness_repr
mc_first_frame_surface_repr = _ffd.surface_repr

__all__ = [
    "mc_first_frame_debug_enabled",
    "mc_first_frame_debug",
    "mc_first_frame_readiness",
    "mc_first_frame_readiness_repr",
    "mc_first_frame_surface_repr",
]
