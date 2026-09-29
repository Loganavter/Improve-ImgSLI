"""Unified in-window drag ghost (carry, row-drag, and all future flows).

Both image-carry (click-to-deliver, ``events/image_carry.py``) and list
row-drag (``events/drag_drop_handler.py``) used to drive
``DragGhostWidget`` directly, duplicating the same ~25 lines: overlay-layer
parent resolution, widget creation, hotspot positioning, per-move
raise + ``ensure_visible``, and ``deleteLater`` cleanup. Any third flow
would have copied them a third time.

This service owns that lifecycle. Callers only decide WHAT the ghost shows
(their pixmap prep stays local: carry scales a file preview, row-drag
grabs the source widget or builds a count badge) and WHERE the hotspot is
(top-right inset for carry, event position / badge center for row-drag).
Delivery semantics (click-to-deliver vs drop targets) stay entirely with
the callers — this class never sees paths, slots, or targets.

Deliberately not QRhi and not QDrag: the ghost lives in the QWidget
content overlay (below the tab strip) where an RHI texture cannot be
cheaply composited, and both flows are in-window only (no OS drop
targets), so a real ``QDrag`` would buy nothing.
"""

from __future__ import annotations

import logging

import shiboken6 as sip
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QPixmap

logger = logging.getLogger("ImproveImgSLI")

# Carry parity: cursor sits near the ghost's top-right so the preview hangs
# bottom-left and never covers the drop target under the cursor.
_DEFAULT_HOTSPOT_INSET = 12


def hotspot_top_right(pixmap: QPixmap, *, inset: float = _DEFAULT_HOTSPOT_INSET) -> QPointF:
    """Hotspot near the pixmap's top-right corner (carry convention)."""
    try:
        return QPointF(
            max(float(inset), float(pixmap.width()) - float(inset)),
            float(inset),
        )
    except Exception:
        return QPointF()


def hotspot_center(pixmap: QPixmap) -> QPointF:
    """Hotspot at the pixmap center (badge convention)."""
    try:
        return QPointF(float(pixmap.width()) / 2.0, float(pixmap.height()) / 2.0)
    except Exception:
        return QPointF()


def _resolve_parent(anchor):
    """(parent_widget, overlay|None) for a ghost anchored at ``anchor``.

    Wave B rule shared by all flows: parent to the content overlay host
    below the tab strip, never the window overlay host. Falls back to the
    anchor's window (startup/test widgets without a layer), ``None`` when
    nothing can host (caller fails soft).
    """
    try:
        from shared_toolkit.ui.overlay_layer import get_content_overlay_layer

        overlay = get_content_overlay_layer(anchor)
    except Exception:
        overlay = None
    if overlay is not None:
        try:
            return overlay.host, overlay
        except Exception:
            pass
    try:
        window = anchor.window() if anchor is not None else None
    except Exception:
        window = None
    parent = window if window is not None else anchor
    return parent, None


class GhostService:
    """Owns one floating ghost widget: show → move* → hide. Never raises."""

    def __init__(self, *, opacity: float = 1.0):
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._widget = None
        self._layer = None
        self._hotspot = QPointF()

    @property
    def is_showing(self) -> bool:
        try:
            return self._widget is not None and bool(sip.isValid(self._widget))
        except Exception:
            return False

    def show(
        self,
        pixmap: QPixmap,
        global_pos,
        *,
        anchor=None,
        hotspot: QPointF | None = None,
    ) -> bool:
        """Show the ghost; ``False`` (no widget, no raise) on any failure."""
        try:
            self.hide()
        except Exception:
            pass
        try:
            if pixmap is None or pixmap.isNull():
                return False
            parent, overlay = _resolve_parent(anchor)
            if parent is None:
                return False
            from ui.widgets.drag_ghost_widget import DragGhostWidget

            widget = DragGhostWidget(parent)
            widget.set_pixmap(pixmap)
            widget.setOpacity(self._opacity)
            self._widget = widget
            self._layer = overlay
            self._hotspot = (
                QPointF(hotspot) if hotspot is not None
                else hotspot_top_right(pixmap)
            )
            self._place(global_pos)
            widget.show()
            widget.raise_()
            self._ensure_visible()
            return True
        except Exception as exc:
            logger.debug("GhostService.show failed: %s", exc)
            try:
                self.hide()
            except Exception:
                pass
            return False

    def move(self, global_pos) -> None:
        """Reposition at ``global_pos`` (QPoint or QPointF); no-op when hidden."""
        if not self.is_showing:
            return
        try:
            self._place(global_pos)
            self._widget.raise_()
            self._ensure_visible()
        except RuntimeError:
            pass
        except Exception as exc:
            logger.debug("GhostService.move failed: %s", exc)

    def hide(self) -> None:
        """Destroy the widget; safe to call anytime (idempotent)."""
        widget, self._widget = self._widget, None
        self._layer = None
        if widget is not None:
            try:
                if sip.isValid(widget):
                    widget.deleteLater()
            except RuntimeError:
                pass
            except Exception as exc:
                logger.debug("GhostService.hide failed: %s", exc)

    # -- internals --

    @staticmethod
    def _to_point(global_pos) -> QPoint:
        if isinstance(global_pos, QPoint):
            return global_pos
        try:
            return global_pos.toPoint()
        except Exception:
            pass
        try:
            return QPoint(int(global_pos.x()), int(global_pos.y()))
        except Exception:
            return QPoint()

    def _place(self, global_pos) -> None:
        top_left = self._to_point(global_pos) - self._hotspot.toPoint()
        self._widget.move(top_left)

    def _ensure_visible(self) -> None:
        layer = self._layer
        if layer is None or not self.is_showing:
            return
        try:
            layer.ensure_visible(self._widget)
        except RuntimeError:
            pass
