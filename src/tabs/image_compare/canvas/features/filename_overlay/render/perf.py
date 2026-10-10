"""``IMGSLI_IC_PERF_DEBUG``-gated timing helpers for the filename overlay.

The CPU supersampled label raster (``raster_ms``), the QRhi resource rebuild
(``ensure_ms``) and the upload/downsample pass are cost centres the frame
spans only see aggregated under ``ic.submit``. These helpers isolate them so
a divider-drag stall can be attributed to the actual stage.

Gated by ``tabs.image_compare.debug.ic_perf_debug`` (flags
``IMGSLI_IC_PERF_DEBUG`` / ``IMGSLI_VIDEO_PERF_DEBUG``); lazy import keeps
the disabled path zero-cost and cycle-free.
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
    name_len: int,
    rw: int,
    rh: int,
    dpr: float,
    interactive: bool,
    quality: int,
    raster_ms: float,
    ensure_ms: float,
) -> None:
    filename_perf(
        "filename.prepare.raster slot=%d name_len=%d label=%dx%d dpr=%.2f "
        "interactive=%s quality=%d raster_ms=%.2f ensure_ms=%.2f",
        slot_index,
        name_len,
        rw,
        rh,
        dpr,
        interactive,
        quality,
        raster_ms,
        ensure_ms,
    )


def log_downsample(ms: float, width: int, height: int) -> None:
    filename_perf(
        "filename.record_pre_pass.downsample upload+pass ms=%.2f final=%dx%d",
        ms,
        width,
        height,
    )


def log_direct_upload(ms: float, width: int, height: int) -> None:
    filename_perf(
        "filename.record_pre_pass.direct upload ms=%.2f final=%dx%d",
        ms,
        width,
        height,
    )
