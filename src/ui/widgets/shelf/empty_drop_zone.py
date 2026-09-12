"""Empty-state drop target for the Session Picker Recent shelf."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from ui.theming import try_resolve_theme_color
from ui.widgets.shelf.layout import EMPTY_DROP_ZONE_H, PANEL_RADIUS

# Tokens for the empty-state drop zone — see plan_app_wide_tokenization.md
# ``shelf.empty.*``. Falls back to the original hardcodes so light-theme
# visuals are preserved until the tokens land in ``themes.json``.
_SHELF_EMPTY_BORDER_TOKEN = "shelf.empty.border"
_SHELF_EMPTY_TITLE_TOKEN = "shelf.empty.title"
_SHELF_EMPTY_HINT_TOKEN = "shelf.empty.hint"
_SHELF_EMPTY_FILL_TOKEN = "shelf.empty.fill"

_SHELF_EMPTY_BORDER_FALLBACK = QColor(120, 120, 120)
_SHELF_EMPTY_TITLE_FALLBACK = QColor(40, 40, 40)
_SHELF_EMPTY_HINT_FALLBACK = QColor(90, 90, 90)


def _resolve_token(token: str, fallback: QColor) -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        tm = ThemeManager.get_instance()
        c = try_resolve_theme_color(tm, token)
        if c is not None and c.isValid():
            return QColor(c)
    except Exception:
        pass
    return QColor(fallback)


def _resolve_title_token() -> QColor:
    # Prefer dedicated token, then generic WindowText, then hardcoded.
    for tok in (_SHELF_EMPTY_TITLE_TOKEN, "WindowText", "dialog.text"):
        try:
            from sli_ui_toolkit.managers import ThemeManager

            tm = ThemeManager.get_instance()
            c = try_resolve_theme_color(tm, tok)
            if c is not None and c.isValid():
                return QColor(c)
        except Exception:
            continue
    return QColor(_SHELF_EMPTY_TITLE_FALLBACK)


def _resolve_hint_token() -> QColor:
    for tok in (_SHELF_EMPTY_HINT_TOKEN, "gallery.header.text", "WindowText"):
        try:
            from sli_ui_toolkit.managers import ThemeManager

            tm = ThemeManager.get_instance()
            c = try_resolve_theme_color(tm, tok)
            if c is not None and c.isValid():
                col = QColor(c)
                # For WindowText fallback reproduce the original 90,90,90 hint
                # as semi-transparent title (mirrors ShelfWidget.colors() hint).
                if tok == "WindowText":
                    col.setAlpha(170)
                return col
        except Exception:
            continue
    return QColor(_SHELF_EMPTY_HINT_FALLBACK)


def _resolve_border_token() -> QColor:
    for tok in (_SHELF_EMPTY_BORDER_TOKEN, "dialog.border", "separator.color", "flyout.border"):
        try:
            from sli_ui_toolkit.managers import ThemeManager

            tm = ThemeManager.get_instance()
            c = try_resolve_theme_color(tm, tok)
            if c is not None and c.isValid():
                return QColor(c)
        except Exception:
            continue
    return QColor(_SHELF_EMPTY_BORDER_FALLBACK)


class EmptyDropZone(QWidget):
    """Dashed DnD placeholder shown when Recent has no pinned projects."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = ""
        self._hint = ""
        self._drag_active = False
        self._border = _resolve_border_token()
        self._title_color = _resolve_title_token()
        self._hint_color = _resolve_hint_token()
        # Fill is transparent by design; try token first, keep transparent fallback.
        self._fill = _resolve_token(_SHELF_EMPTY_FILL_TOKEN, QColor(0, 0, 0, 0))
        if self._fill.alpha() != 0:
            # Token should remain subtle; if opaque token sneaks in, keep it.
            pass
        else:
            self._fill = QColor(0, 0, 0, 0)
        self.setObjectName("RecentEmptyDropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(scaled_px(EMPTY_DROP_ZONE_H))
        self.setMinimumHeight(scaled_px(EMPTY_DROP_ZONE_H))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

    def set_texts(self, *, title: str, hint: str) -> None:
        self._title = str(title or "")
        self._hint = str(hint or "")
        self.update()

    def reapply_scaled_height(self) -> None:
        """Re-apply the scale-dependent fixed height after a live UiScale change."""
        self.setFixedHeight(scaled_px(EMPTY_DROP_ZONE_H))
        self.setMinimumHeight(scaled_px(EMPTY_DROP_ZONE_H))

    def set_drag_active(self, active: bool) -> None:
        active = bool(active)
        if self._drag_active == active:
            return
        self._drag_active = active
        self.update()

    def set_palette_colors(
        self,
        *,
        border: QColor,
        title: QColor,
        hint: QColor,
        fill: QColor | None = None,
    ) -> None:
        self._border = QColor(border)
        self._title_color = QColor(title)
        self._hint_color = QColor(hint)
        if fill is not None:
            self._fill = QColor(fill)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, PANEL_RADIUS - 2, PANEL_RADIUS - 2)

        if self._fill.alpha() > 0:
            painter.fillPath(path, self._fill)

        pen = QPen(self._border, 1.6 if self._drag_active else 1.25)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setDashPattern([5.0, 4.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        mid_y = rect.center().y()
        title_font = ui_font(pixel_size=14)
        title_font.setBold(True)
        hint_font = ui_font(pixel_size=12)

        title_fm = QFontMetrics(title_font)
        hint_fm = QFontMetrics(hint_font)
        gap = scaled_px(6)
        block_h = title_fm.height()
        if self._hint:
            block_h += gap + hint_fm.height()
        top = mid_y - block_h / 2.0

        if self._title:
            painter.setFont(title_font)
            painter.setPen(self._title_color)
            painter.drawText(
                int(rect.left() + scaled_px(16)),
                int(top),
                int(rect.width() - scaled_px(32)),
                title_fm.height(),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )
            top += title_fm.height() + gap

        if self._hint:
            painter.setFont(hint_font)
            painter.setPen(self._hint_color)
            painter.drawText(
                int(rect.left() + scaled_px(16)),
                int(top),
                int(rect.width() - scaled_px(32)),
                hint_fm.height(),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                self._hint,
            )

        painter.end()