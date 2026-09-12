"""In-window drag ghost (host-owned; not part of sli-ui-toolkit)."""

from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from sli_ui_toolkit.ui.inspector.spec import InspectSpec  # noqa: E402

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import ui_font


def make_count_slot_pixmap(template: QWidget, count: int) -> QPixmap:
    """Slot-shaped ghost with a centered count (multi-select drag)."""
    size = template.size()
    if size.width() < 8 or size.height() < 8:
        size = template.sizeHint()
    width = max(scaled_px(48), int(size.width()))
    height = max(scaled_px(28), int(size.height()))
    pixmap = QPixmap(QSize(width, height))
    pixmap.fill(Qt.GlobalColor.transparent)

    try:
        from sli_ui_toolkit.theme import ThemeManager

        from ui.theming import try_resolve_theme_color

        tm = ThemeManager.get_instance()

        def _resolve(token: str, fallback: QColor) -> QColor:
            try:
                c = try_resolve_theme_color(tm, token)
                if c is not None and c.isValid():
                    return QColor(c)
            except Exception:
                pass
            return QColor(fallback)

        fill = _resolve("list_item.background.hover", QColor(240, 240, 240))
        accent = _resolve("accent", QColor("#0078D4"))
        # list_item.text.normal may be absent in dark; chain to WindowText
        text_resolved = try_resolve_theme_color(tm, "list_item.text.normal")
        if text_resolved is not None and text_resolved.isValid():
            text = QColor(text_resolved)
        else:
            text_alt = try_resolve_theme_color(tm, "WindowText")
            text = QColor(text_alt) if text_alt is not None and text_alt.isValid() else QColor(30, 30, 30)
    except Exception:
        fill = QColor(240, 240, 240)
        accent = QColor("#0078D4")
        text = QColor(30, 30, 30)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    rect = pixmap.rect().adjusted(2, 2, -2, -2)
    path = QPainterPath()
    path.addRoundedRect(rect, 8.0, 8.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawPath(path)

    pen = painter.pen()
    pen.setColor(accent)
    pen.setWidth(scaled_px(3))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    x = rect.left() + scaled_px(3)
    painter.drawLine(x, rect.top() + scaled_px(7), x, rect.bottom() - scaled_px(7))

    font = ui_font(pixel_size=16, bold=True)
    painter.setFont(font)
    painter.setPen(text)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), str(max(1, int(count))))
    painter.end()
    return pixmap


class DragGhostWidget(QWidget):
    def __init__(self, parent=None):
        if parent is None:
            raise ValueError("DragGhostWidget requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap = QPixmap()
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self.setOpacity(1.0)

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.setFixedSize(pixmap.size())
        self.update()

    def setOpacity(self, opacity):
        self._opacity_effect.setOpacity(max(0.0, min(1.0, float(opacity))))

    def move(self, pos):
        if isinstance(pos, QPoint) and self.parentWidget() is not None:
            return super().move(self.parentWidget().mapFromGlobal(pos))
        return super().move(pos)

    def paintEvent(self, event):
        if self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 8.0, 8.0)
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), self._pixmap)

DragGhostWidget.inspect_spec = InspectSpec(
    family="DragGhostWidget",
    docs="docs/dev/widgets/drag_ghost_widget.md",
    regions=True,
    layers=True,
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
DragGhostWidget.widget_descriptor = WidgetDescriptor(
    family=DragGhostWidget.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(DragGhostWidget.inspect_spec, 'config', ()),
        state=DragGhostWidget.inspect_spec.state,
        token_family=getattr(DragGhostWidget.inspect_spec, 'token_family', ()),
        regions=getattr(DragGhostWidget.inspect_spec, 'regions', False),
        layers=getattr(DragGhostWidget.inspect_spec, 'layers', False),
        docs=getattr(DragGhostWidget.inspect_spec, 'docs', ''),
        preview_seed=getattr(DragGhostWidget.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(DragGhostWidget.inspect_spec, 'apply_config_refresh', None),
    ),
)
