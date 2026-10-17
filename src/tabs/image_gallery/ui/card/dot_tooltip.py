"""Per-dot hover tooltip for gallery cards/list rows.

The overlay painters stash ``_gallery_dot_geometry`` (dot x-centers + the
parallel ``(label, score)`` info list) on the widget. This filter maps a
``QEvent.Type.ToolTip`` cursor x onto that geometry and shows
``"<label>: <N>%"``; off a dot it falls through to the widget's normal
tooltip.

Tooltip rendering goes through the toolkit ``PathTooltip`` bubble (the app
forbids direct ``QToolTip`` — ``tests/contracts/test_no_system_tooltips.py``).
``_disable_custom_tooltip`` turns the app-wide interceptor off for this
widget so the filter owns both the dot text and the fallback tooltip; the
visual result is the same in-window bubble.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject

from tabs.image_gallery.ui.card.dots import dot_tooltip_text


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


def _global_pos(watched, event):
    try:
        return event.globalPos()
    except Exception:
        try:
            return watched.mapToGlobal(watched.rect().center())
        except Exception:
            return None


def dot_tooltip_text_at(card, x) -> str | None:
    """``"<label>: <N>%"`` for the dot nearest *x*, or None off the dots.

    Hit test is one-dimensional (x only): the dot row is a single line, so
    a vertical tolerance would only make the tooltip sticky over the whole
    text band. ``pitch / 2`` is the natural Voronoi cell of each dot.
    """
    geometry = getattr(card, "_gallery_dot_geometry", None)
    if not isinstance(geometry, dict):
        return None
    centers = geometry.get("x_centers") or ()
    infos = geometry.get("infos") or ()
    if not centers or len(centers) != len(infos):
        return None
    try:
        cursor_x = float(x)
    except Exception:
        return None
    try:
        pitch = float(geometry.get("pitch") or 14.0)
    except Exception:
        pitch = 14.0
    best_index = -1
    best_distance = None
    for index, center in enumerate(centers):
        try:
            distance = abs(cursor_x - float(center))
        except Exception:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
    if best_index < 0 or best_distance is None:
        return None
    if best_distance > max(5.0, pitch / 2.0):
        return None
    try:
        return dot_tooltip_text(infos[best_index])
    except Exception:
        return None


class _CardDotTooltipFilter(QObject):
    """Show the per-dot metric tooltip on ``ToolTip`` events for one card."""

    def __init__(self, card) -> None:
        super().__init__(card)
        self._card = card

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            if event.type() != QEvent.Type.ToolTip:
                return False
        except Exception:
            return False
        text = ""
        try:
            text = dot_tooltip_text_at(self._card, _local_x(self._card, event)) or ""
        except Exception:
            text = ""
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
        return True


def ensure_dot_tooltip(card) -> None:
    """Install the per-dot tooltip filter on *card* (idempotent, pool-safe)."""
    try:
        if getattr(card, "_gallery_dot_tooltip_installed", False):
            return
        filt = _CardDotTooltipFilter(card)
        card.installEventFilter(filt)
        card._gallery_dot_tooltip_installed = True  # type: ignore[attr-defined]
        card._gallery_dot_tooltip_filter = filt  # type: ignore[attr-defined]
        # The app-wide bubble interceptor would consume the ToolTip event
        # before this widget-level filter (app filters run first) — this
        # filter shows the normal tooltip itself when off a dot.
        card._disable_custom_tooltip = True  # type: ignore[attr-defined]
    except Exception:
        pass
