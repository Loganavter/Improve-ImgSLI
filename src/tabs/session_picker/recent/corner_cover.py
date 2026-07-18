"""AA rounded corner cover for the Recent items viewport (no binary mask)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from tabs.session_picker.recent.layout import PANEL_RADIUS


class ViewportCornerCover(QWidget):
    """Paints shelf-colored corners over a rectangular content fill.

    OverlayScrollArea's ``set_corner_radius`` uses a 1-bit mask that fights the
    main-window CSD clip. This cover keeps AA rounding without ``setMask``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = PANEL_RADIUS,
    ) -> None:
        super().__init__(parent)
        self._radius = float(radius)
        self._color = QColor(0, 0, 0)
        self.setObjectName("RecentViewportCornerCover")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_color(self, color: QColor) -> None:
        fill = QColor(color)
        fill.setAlpha(255)
        if self._color == fill:
            return
        self._color = fill
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        outer = QPainterPath()
        outer.addRect(rect)
        inner = QPainterPath()
        inset = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(self._radius, inset.width() / 2.0, inset.height() / 2.0)
        inner.addRoundedRect(inset, radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(outer.subtracted(inner), self._color)
        painter.end()


class ViewportCornerCoverSync(QObject):
    """Keeps a corner cover aligned with an OverlayScrollArea viewport."""

    def __init__(self, scroll: QWidget, cover: ViewportCornerCover) -> None:
        super().__init__(scroll)
        self._scroll = scroll
        self._cover = cover
        cover.setParent(scroll)
        scroll.installEventFilter(self)
        viewport = getattr(scroll, "viewport", None)
        if callable(viewport) and viewport() is not None:
            viewport().installEventFilter(self)
        self.sync()

    def sync(self) -> None:
        viewport = getattr(self._scroll, "viewport", None)
        if not callable(viewport):
            return
        vp = viewport()
        if vp is None:
            return
        self._cover.setGeometry(vp.geometry())
        self._cover.raise_()
        bar = getattr(self._scroll, "custom_v_scrollbar", None)
        if bar is not None:
            bar.raise_()
        self._cover.show()

    def eventFilter(self, obj, event):  # noqa: N802
        et = event.type()
        if et in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Move,
        ):
            self.sync()
        return super().eventFilter(obj, event)
