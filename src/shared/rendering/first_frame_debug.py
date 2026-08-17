"""Env-gated first-frame timeline shared by both canvas tabs.

``IMGSLI_<TAB>_FIRST_FRAME_DEBUG``-gated first-frame diagnostics: logs the
ordering and timing of canvas construction → first show → renderer
initialize → each painted present → ``firstFrameRendered`` emission →
startup-placeholder hide, so a blank/stale first frame can be pinned to
which step ran before the engine was ready.

Same convention as ``ui/widgets/flyout_debug.py``: gate on an env var, tag
every line with a unique bracketed prefix, near-zero overhead when disabled.

Both canvas tabs used to carry byte-identical mirrors of this module with
``ic_``/``mc_`` name prefixes; the per-tab wrapper modules (one per canvas
tab, keeping their own env gates and timeline state) now bind this shared
implementation.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("ImproveImgSLI")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


class FirstFrameDebug:
    """First-frame timeline instrumentation parameterized per canvas tab.

    Parameters:
        env_name: env var that gates the instrumentation.
        log_tag: bracketed prefix for every log line (e.g. ``ic-first-frame``).
        attr_prefix: widget attribute prefix for origin/last timestamps
            (keeps the two tabs' widgets from sharing timeline state).
        renderer_attr: attribute on the widget that holds the renderer
            (``_rhi_renderer`` for Image Compare, ``_renderer`` for Multi
            Compare).
        composition_attr: widget attribute that holds the resolved render
            plan / composition (``_active_render_plan`` vs
            ``_active_composition``).
    """

    def __init__(
        self,
        env_name: str,
        log_tag: str,
        attr_prefix: str,
        renderer_attr: str,
        composition_attr: str,
    ) -> None:
        self._env_name = env_name
        self._log_tag = log_tag
        self._origin_attr = f"{attr_prefix}_origin"
        self._last_attr = f"{attr_prefix}_last"
        self._renderer_attr = renderer_attr
        self._composition_attr = composition_attr

    def enabled(self) -> bool:
        return _env_flag(self._env_name)

    def debug(self, widget, message: str, *args) -> None:
        """Record one first-frame timeline event on ``widget``.

        The first call on a given widget establishes its ``t=0``; later calls
        log as ``+<ms> (<+delta>ms)`` so the log reads as a timeline. No-op
        unless the env gate is set.
        """
        if not self.enabled():
            return
        try:
            now = time.monotonic()
            origin = getattr(widget, self._origin_attr, None)
            if origin is None:
                origin = now
                setattr(widget, self._origin_attr, origin)
            last = getattr(widget, self._last_attr, None)
            delta = 0.0 if last is None else (now - last) * 1000.0
            try:
                setattr(widget, self._last_attr, now)
            except Exception:
                pass
            total_ms = (now - origin) * 1000.0
        except Exception:
            total_ms = 0.0
            delta = 0.0
        logger.info(
            "[%s] +%9.1fms (+%7.1fms)  %s  %s",
            self._log_tag,
            total_ms,
            delta,
            self._widget_tag(widget),
            (message % args) if args else message,
        )

    def readiness(self, widget) -> dict:
        """Snapshot of "is this frame actually ready" at an event.

        Textures-resident count comes from the renderer's tile service; the
        composition flag tells whether a resolved render plan exists at all.
        Cheap enough to call on every logged event (env-gated).
        """
        out = {"textures_resident": 0, "composition": False}
        try:
            renderer = getattr(widget, self._renderer_attr, None)
            if renderer is not None:
                tile_service = getattr(renderer, "tile_service", None)
                if tile_service is not None:
                    count = 0
                    for key in list(tile_service._resident or {}):
                        count += len(tile_service.resident_tiles(key) or ())
                    out["textures_resident"] = count
                out["composition"] = (
                    getattr(widget, self._composition_attr, None) is not None
                )
        except Exception:
            pass
        return out

    def readiness_repr(self, widget) -> str:
        data = self.readiness(widget)
        return (
            f"textures_resident={data['textures_resident']} "
            f"composition={'yes' if data['composition'] else 'no'}"
        )

    def _grab_opaque_fraction(self, widget) -> float:
        """Opaque-pixel fraction of a small corner grab of the widget (Qt-side).

        ``1.0`` = the widget region reads fully opaque from Qt's point of view;
        ``0.0`` = fully transparent; ``-1.0`` = unavailable (not shown / grab
        failed). This is what the compositor-side of Qt thinks the canvas
        shows, independent of the RHI present count.
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

    def surface_repr(self, widget) -> str:
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
        opaque = self._grab_opaque_fraction(widget)
        return (
            f"visible={visible} exposed={exposed} "
            f"grab_opaque={opaque:.2f}"
            if isinstance(opaque, float)
            else f"visible={visible} exposed={exposed} grab_opaque={opaque}"
        )

    def _widget_tag(self, widget) -> str:
        """Short identity for the logged canvas so a run with several canvas
        instances (page re-creation, offscreen previews, ...) stays readable.

        ``P`` marks the primary live page canvas (the widget sets
        ``_ffd_primary``); ``#<id>@<parent-type>`` distinguishes instances.
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
