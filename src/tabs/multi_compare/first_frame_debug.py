"""``IMGSLI_MC_FIRST_FRAME_DEBUG``-gated first-frame timeline for Multi Compare.

Diagnoses "the QRhi engine doesn't manage to prepare the first frame before
it's shown": logs the ordering and timing of canvas construction → first
show → renderer initialize → each painted present → ``firstFrameRendered``
emission → startup-placeholder hide, so a blank/stale first frame can be
pinned to which step ran before the engine was ready.

Same convention as ``shared/rendering/render_debug.py`` /
``ui/widgets/flyout_debug.py``: gate on an env var, tag every line with a
unique bracketed prefix, near-zero overhead when disabled.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("ImproveImgSLI")

_ORIGIN_ATTR = "_mc_first_frame_debug_origin"
_LAST_ATTR = "_mc_first_frame_debug_last"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def mc_first_frame_debug_enabled() -> bool:
    return _env_flag("IMGSLI_MC_FIRST_FRAME_DEBUG")


def _elapsed_ms(widget) -> float:
    """Monotonic ms since this widget's first debug event (or 0 before any)."""
    origin = getattr(widget, _ORIGIN_ATTR, None)
    if origin is None:
        origin = time.monotonic()
        try:
            setattr(widget, _ORIGIN_ATTR, origin)
        except Exception:
            pass
    return (time.monotonic() - origin) * 1000.0


def _widget_tag(widget) -> str:
    """Short identity for the logged canvas so a run with several canvas
    instances (page re-creation, offscreen previews, ...) stays readable.

    ``P`` marks the primary live page canvas (the widget sets ``_ffd_primary``);
    ``#<id>@<parent-type>`` distinguishes instances.
    """
    try:
        parent = None
        if hasattr(widget, "parentWidget"):
            try:
                parent = widget.parentWidget()
            except Exception:
                parent = None
        parent_name = type(parent).__name__ if parent is not None else "root"
        ident = str(hex(id(widget)))[-6:]
        primary = "P" if getattr(widget, "_ffd_primary", False) else "."
        return f"{primary}#{ident}@{parent_name}"
    except Exception:
        return "?"


def mc_first_frame_debug(widget, message: str, *args) -> None:
    """Record one first-frame timeline event on ``widget``.

    The first call on a given widget establishes its ``t=0``; later calls
    log as ``+<ms> (<+delta>ms)`` so the log reads as a timeline. No-op
    unless ``IMGSLI_MC_FIRST_FRAME_DEBUG`` is set.
    """
    if not mc_first_frame_debug_enabled():
        return
    try:
        now = time.monotonic()
        origin = getattr(widget, _ORIGIN_ATTR, None)
        if origin is None:
            origin = now
            setattr(widget, _ORIGIN_ATTR, origin)
        last = getattr(widget, _LAST_ATTR, None)
        delta = 0.0 if last is None else (now - last) * 1000.0
        try:
            setattr(widget, _LAST_ATTR, now)
        except Exception:
            pass
        total_ms = (now - origin) * 1000.0
    except Exception:
        total_ms = 0.0
        delta = 0.0
    logger.info(
        "[mc-first-frame] +%9.1fms (+%7.1fms)  %s  %s",
        total_ms,
        delta,
        _widget_tag(widget),
        (message % args) if args else message,
    )


def mc_first_frame_readiness(widget) -> dict:
    """Snapshot of "is this frame actually ready" at an event.

    Textures-resident count comes from the renderer's tile service; the
    composition flag tells whether a resolved render plan exists at all.
    Cheap enough to call on every logged event (env-gated).
    """
    out = {"textures_resident": 0, "composition": False}
    try:
        renderer = getattr(widget, "_renderer", None)
        if renderer is not None:
            tile_service = getattr(renderer, "tile_service", None)
            if tile_service is not None:
                count = 0
                for key in list(tile_service._resident or {}):
                    count += len(tile_service.resident_tiles(key) or ())
                out["textures_resident"] = count
            out["composition"] = getattr(widget, "_active_composition", None) is not None
    except Exception:
        pass
    return out


def mc_first_frame_readiness_repr(widget) -> str:
    data = mc_first_frame_readiness(widget)
    return (
        f"textures_resident={data['textures_resident']} "
        f"composition={'yes' if data['composition'] else 'no'}"
    )


def _grab_opaque_fraction(widget) -> float:
    """Opaque-pixel fraction of a small corner grab of the widget (Qt-side).

    ``1.0`` = the widget region reads fully opaque from Qt's point of view;
    ``0.0`` = fully transparent; ``-1.0`` = unavailable (not shown / grab
    failed). This is what the compositor-side of Qt thinks the canvas shows,
    independent of the RHI present count — a transparent grab while presents
    are being recorded pinpoints a present that never reached the display.
    """
    try:
        from PySide6.QtCore import QRect

        w, h = widget.width(), widget.height()
        if w <= 0 or h <= 0:
            return -1.0
        img = widget.grab(QRect(0, 0, min(w, 96), min(h, 96))).toImage()
        if img.isNull():
            return -1.0
        opaque = total = 0
        step = 6
        for y in range(0, img.height(), step):
            for x in range(0, img.width(), step):
                total += 1
                if img.pixelColor(x, y).alpha() >= 255:
                    opaque += 1
        return (opaque / total) if total else -1.0
    except Exception:
        return -1.0


def mc_first_frame_surface_repr(widget) -> str:
    """Snapshot of what the canvas region actually shows on screen."""
    try:
        visible = widget.isVisible() if hasattr(widget, "isVisible") else None
    except Exception:
        visible = None
    try:
        window = widget.window() if hasattr(widget, "window") else None
        handle = (
            window.windowHandle()
            if window is not None and hasattr(window, "windowHandle")
            else None
        )
        exposed = (
            handle.isExposed()
            if handle is not None and hasattr(handle, "isExposed")
            else None
        )
    except Exception:
        exposed = None
    opaque = _grab_opaque_fraction(widget)
    return (
        f"visible={visible} exposed={exposed} "
        f"grab_opaque={opaque:.2f}"
        if isinstance(opaque, float)
        else f"visible={visible} exposed={exposed} grab_opaque={opaque}"
    )
