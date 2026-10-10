"""``IMGSLI_IC_PERF_DEBUG``-gated timing for the filename-overlay raster.

Re-added for variant A diagnosis: the text-only texture is cached by content,
so a split-drag should NOT re-raster every frame -- this log proves whether it
does, and how long a re-raster costs, so "lag is back" can be attributed to
raster churn vs something else.

Gated by ``tabs.image_compare.debug.ic_perf_debug`` (flags
``IMGSLI_IC_PERF_DEBUG`` / ``IMGSLI_VIDEO_PERF_DEBUG``); lazy import keeps the
disabled path zero-cost.
"""

from __future__ import annotations


def filename_perf_enabled() -> bool:
    try:
        from tabs.image_compare.debug import ic_perf_debug_enabled

        return ic_perf_debug_enabled()
    except Exception:
        return False


def filename_perf(msg: str, *args) -> None:
    try:
        from tabs.image_compare.debug import ic_perf_debug

        ic_perf_debug(msg, *args)
    except Exception:
        pass


def log_prepare_raster(
    slot_index: int,
    elided: str,
    text_w: int,
    rh: int,
    dpr: float,
    quality: int,
    interactive: bool,
    changed: str,
    raster_ms: float,
    ensure_ms: float,
) -> None:
    filename_perf(
        "filename.prepare.raster slot=%d text=%dpxx%d elided_len=%d dpr=%.2f "
        "quality=%d interactive=%s changed=[%s] raster_ms=%.2f ensure_ms=%.2f",
        slot_index,
        text_w,
        rh,
        len(elided),
        dpr,
        quality,
        interactive,
        changed,
        raster_ms,
        ensure_ms,
    )
