"""Per-dot hover tooltip for gallery cards/list rows.

The overlay painters stash ``_gallery_dot_geometry`` (per-dot ``(x, y)`` centers
+ the parallel ``(label, score)`` info list) on the widget. This filter maps a
``QEvent.Type.ToolTip`` cursor position onto that geometry and shows
``"<label>: <N>%"``; off a dot it falls through to the widget's normal
tooltip.

Tooltip rendering goes through the toolkit ``PathTooltip`` bubble (the app
forbids direct ``QToolTip`` — ``tests/contracts/test_no_system_tooltips.py``).
``_disable_custom_tooltip`` turns the app-wide interceptor off for this
widget so the filter owns both the dot text and the fallback tooltip; the
visual result is the same in-window bubble.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject

from tabs.image_gallery.ui.card.dots import DOT_DIAMETER, DOT_PITCH, dot_tooltip_text


def _local_x(watched, event) -> float | None:
    """Cursor x in widget coordinates (event position first, global as backup)."""
    try:
        pos = event.pos()
        if pos is not None:
            return float(pos.x())
    except Exception:
        pass
    try:
        return float(watched.mapFromGlobal(event.globalPos()).x())
    except Exception:
        return None


def _local_y(watched, event) -> float | None:
    """Cursor y in widget coordinates (event position first, global as backup)."""
    try:
        pos = event.pos()
        if pos is not None:
            return float(pos.y())
    except Exception:
        pass
    try:
        return float(watched.mapFromGlobal(event.globalPos()).y())
    except Exception:
        return None


def _global_pos(watched, event):
    try:
        return event.globalPosition().toPoint()
    except Exception:
        pass
    try:
        return event.globalPos()
    except Exception:
        try:
            return watched.mapToGlobal(watched.rect().center())
        except Exception:
            return None


def _geometry_centers(geometry) -> list[tuple[float, float | None]]:
    """Per-dot ``(x, y | None)`` centers from the stashed geometry dict.

    Preferred key is ``"centers"`` (wrapped rows, both axes). The legacy
    ``"x_centers"`` + ``"y_center"`` pair is still accepted for older readers;
    its ``y`` may be None when no ``y_center`` was recorded.
    """
    raw = geometry.get("centers")
    centers: list[tuple[float, float | None]] = []
    if raw:
        for entry in raw:
            try:
                cx, cy = entry
                centers.append((float(cx), float(cy)))
            except Exception:
                continue
        if centers:
            return centers
    y0 = geometry.get("y_center")
    try:
        y0 = float(y0) if y0 is not None else None
    except Exception:
        y0 = None
    for entry in geometry.get("x_centers") or ():
        try:
            centers.append((float(entry), y0))
        except Exception:
            continue
    return centers


def dot_tooltip_text_at(card, x, y=None) -> str | None:
    """``"<label>: <N>%"`` for the dot at cursor ``(x, y)``, or None off a dot.

    The dot block may WRAP into several rows, so the hit test is two
    dimensional: the nearest dot center within the dot radius (``DOT_DIAMETER``
    / 2) wins; a point between rows resolves to nothing. When ``y`` is omitted
    (legacy callers) the test degrades to the old one-dimensional x-only
    Voronoi cell (``pitch / 2``).
    """
    geometry = getattr(card, "_gallery_dot_geometry", None)
    if not isinstance(geometry, dict):
        return None
    infos = geometry.get("infos") or ()
    centers = _geometry_centers(geometry)
    if not centers or len(centers) != len(infos):
        return None
    try:
        cursor_x = float(x)
    except Exception:
        return None
    cursor_y: float | None = None
    if y is not None:
        try:
            cursor_y = float(y)
        except Exception:
            cursor_y = None
    try:
        pitch = float(geometry.get("pitch") or DOT_PITCH)
    except Exception:
        pitch = DOT_PITCH
    # Two-dimensional only when the caller supplied y and every center has one.
    use_y = cursor_y is not None and all(cy is not None for _cx, cy in centers)
    radius = float(DOT_DIAMETER) / 2.0
    best_index = -1
    best_distance = None
    for index, (cx, cy) in enumerate(centers):
        dx = cursor_x - cx
        if use_y:
            distance = math.hypot(dx, cursor_y - float(cy))  # type: ignore[arg-type]
        else:
            distance = abs(dx)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    if best_index < 0 or best_distance is None:
        return None
    limit = radius if use_y else max(5.0, pitch / 2.0)
    if best_distance > limit:
        return None
    try:
        return dot_tooltip_text(infos[best_index])
    except Exception:
        return None


class _CardDotTooltipFilter(QObject):
    """Show the per-dot metric tooltip on ``ToolTip`` / ``MouseMove`` events.

    ``ToolTip`` shows the bubble (``delay_ms=0`` — the widget's own tooltip was
    suppressed); ``MouseMove`` refreshes it INSTANTLY when the cursor crosses
    dot-to-dot inside the same card (Qt sends no ``Enter`` within one widget and
    re-delays the next ``ToolTip`` event), gated on ``PathTooltip``'s live
    session so a first hover still pays the normal delay.
    """

    def __init__(self, card) -> None:
        super().__init__(card)
        self._card = card
        self._shown_text: str | None = None

    def _dot_text_at_event(self, event) -> str:
        try:
            return (
                dot_tooltip_text_at(
                    self._card,
                    _local_x(self._card, event),
                    _local_y(self._card, event),
                )
                or ""
            )
        except Exception:
            return ""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            et = event.type()
        except Exception:
            return False
        if et == QEvent.Type.ToolTip:
            text = self._dot_text_at_event(event)
            if not text:
                try:
                    text = str(self._card.toolTip() or "")
                except Exception:
                    text = ""
            if not text:
                return False
            global_pos = _global_pos(self._card, event)
            if global_pos is None:
                return False
            try:
                from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip

                PathTooltip.get_instance().show_tooltip(global_pos, text, delay_ms=0)
            except Exception:
                return False
            self._shown_text = text
            return True
        if et == QEvent.Type.MouseMove:
            text = self._dot_text_at_event(event)
            if not text:
                self._shown_text = None
                return False
            if text == self._shown_text:
                return False
            try:
                from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip

                pt = PathTooltip.get_instance()
            except Exception:
                return False
            if not pt.session_active():
                return False
            global_pos = _global_pos(self._card, event)
            if global_pos is None:
                return False
            try:
                pt.show_tooltip(global_pos, text, delay_ms=0)
            except Exception:
                return False
            self._shown_text = text
            return False
        return False


def ensure_dot_tooltip(card) -> None:
    """Install the per-dot tooltip filter on *card* (idempotent, pool-safe)."""
    try:
        if getattr(card, "_gallery_dot_tooltip_installed", False):
            return
        filt = _CardDotTooltipFilter(card)
        card.installEventFilter(filt)
        # MouseMove refreshes a dot-to-dot move instantly (no cross-widget Enter
        # inside one card); tracking is required for MouseMove delivery.
        try:
            card.setMouseTracking(True)
        except Exception:
            pass
        card._gallery_dot_tooltip_installed = True  # type: ignore[attr-defined]
        card._gallery_dot_tooltip_filter = filt  # type: ignore[attr-defined]
        # The app-wide bubble interceptor would consume the ToolTip event
        # before this widget-level filter (app filters run first) — this
        # filter shows the normal tooltip itself when off a dot.
        card._disable_custom_tooltip = True  # type: ignore[attr-defined]
    except Exception:
        pass
