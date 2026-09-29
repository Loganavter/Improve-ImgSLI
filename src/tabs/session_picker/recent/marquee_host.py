"""In-paint marquee host for the recent-projects shelf (thin consumer shell).

The mechanism is canonical in the toolkit
(``sli_ui_toolkit.widgets.MarqueeState`` + ``paint_marquee_band``); this
module only provides the shelf's content host: an ``OpaqueFillHost`` that
keeps a band rect and paints it via the toolkit helper. No tracker logic
here — see ``recent/marquee.py`` for the gesture wiring.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import marquee_dirty_rect, paint_marquee_band

from ui.widgets.shelf import OpaqueFillHost


def _default_accent() -> QColor:
    try:
        from ui.widgets.shelf.selection import selection_accent_color

        accent = selection_accent_color()
        if accent is not None and accent.isValid():
            return QColor(accent)
    except Exception:
        pass
    return QColor("#0078D4")


class MarqueeHost(OpaqueFillHost):
    """Content host that paints the selection band in its own paint pass.

    Subclass — the shared ``OpaqueFillHost`` is never modified (gallery
    shelf unaffected). The band paints after the base fill and before
    children (cards), i.e. under the cards. Paint clips to widget bounds
    inherently.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.band_rect: QRect | None = None
        self._band_accent = _default_accent()

    def set_accent(self, color) -> None:  # type: ignore[no-untyped-def]
        try:
            accent = QColor(color)
            if accent.isValid():
                self._band_accent = accent
                if self.band_rect is not None:
                    self.update()
        except Exception:
            pass

    def set_band_rect(self, rect: QRect | None) -> None:
        """Assign the band (host-local), repainting the changed region only."""
        try:
            norm = QRect(rect) if rect is not None and rect.isValid() and not rect.isEmpty() else None
        except Exception:
            norm = None
        try:
            if norm == self.band_rect or (norm is not None and self.band_rect is not None and norm == self.band_rect):
                return
        except Exception:
            pass
        old = self.band_rect
        self.band_rect = norm
        try:
            if old is None and norm is None:
                self.update()
            elif old is None:
                self.update(norm.adjusted(-1, -1, 1, 1))
            elif norm is None:
                self.update(old.adjusted(-1, -1, 1, 1))
            else:
                self.update(old.united(norm).adjusted(-1, -1, 1, 1))
        except Exception:
            try:
                self.update()
            except Exception:
                pass

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        rect = self.band_rect
        if rect is None or rect.isEmpty() or not rect.isValid():
            return
        try:
            from PySide6.QtGui import QPainter

            painter = QPainter(self)
            try:
                paint_marquee_band(painter, rect, self._band_accent)
            finally:
                painter.end()
        except Exception:
            pass
