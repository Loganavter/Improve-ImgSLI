from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from ui.widgets.canvas.render_common import new_overlay_image
from ui.widgets.canvas.render_metrics import resolve_screen_px
from tabs.image_compare.canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS

_BUTTON_BG = QColor(28, 34, 45, 218)
_BUTTON_BG_HOVER = QColor(42, 54, 74, 238)
_BUTTON_BORDER = QColor(255, 255, 255, 172)
_BUTTON_BORDER_HOVER = QColor(100, 150, 255, 230)
_CANCEL_BG = QColor(242, 244, 248, 232)
_CANCEL_BG_HOVER = QColor(255, 255, 255, 248)
_CANCEL_BORDER = QColor(100, 110, 128, 220)
_CANCEL_ICON = QColor(54, 60, 72, 240)


def _draw_paste_button(
    painter: QPainter,
    rect: QRectF,
    text: str,
    hovered: bool,
    metrics,
) -> None:
    visual_width = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_width_du,
        metrics,
    )
    visual_height = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_height_du,
        metrics,
    )
    radius = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_radius_du,
        metrics,
    )
    border_width = resolve_screen_px(
        (
            DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_hover_du
            if hovered
            else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_du
        ),
        metrics,
    )
    center = rect.center()
    visual_rect = QRectF(
        center.x() - (visual_width / 2.0),
        center.y() - (visual_height / 2.0),
        visual_width,
        visual_height,
    )

    if hovered:
        bg_color = _BUTTON_BG_HOVER
        text_color = QColor(255, 255, 255)
        border_color = _BUTTON_BORDER_HOVER
    else:
        bg_color = _BUTTON_BG
        text_color = QColor(248, 248, 248)
        border_color = _BUTTON_BORDER

    painter.setPen(QPen(border_color, border_width))
    painter.setBrush(bg_color)
    painter.drawRoundedRect(visual_rect, radius, radius)

    font = QFont(painter.font())
    font.setPixelSize(
        max(
            1,
            int(
                round(
                    resolve_screen_px(
                        (
                            DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_hover_base_du
                            if hovered
                            else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_base_du
                        ),
                        metrics,
                    )
                )
            ),
        )
    )
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setBold(hovered)
    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(visual_rect, Qt.AlignmentFlag.AlignCenter, text)


def _draw_paste_overlay(painter: QPainter, widget, metrics) -> None:
    state = widget.runtime_state
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return

    backdrop_alpha = max(
        0,
        min(
            255,
            int(round(DEFAULT_CANVAS_STYLE_TOKENS.overlay_backdrop_alpha)),
        ),
    )
    painter.fillRect(0, 0, width, height, QColor(0, 0, 0, backdrop_alpha))

    buttons = []
    texts = state._paste_overlay_texts
    rects = state._paste_overlay_rects
    if not rects["up"].isNull():
        buttons.append(("up", rects["up"], texts.get("up", "")))
    if not rects["down"].isNull():
        buttons.append(("down", rects["down"], texts.get("down", "")))
    if not rects["left"].isNull():
        buttons.append(("left", rects["left"], texts.get("left", "")))
    if not rects["right"].isNull():
        buttons.append(("right", rects["right"], texts.get("right", "")))

    for direction, rect, text in buttons:
        _draw_paste_button(
            painter,
            rect,
            text,
            state._paste_overlay_hovered_button == direction,
            metrics,
        )

    cancel_rect = rects["cancel"]
    if cancel_rect.isNull():
        return
    is_cancel_hovered = state._paste_overlay_hovered_button == "cancel"
    cancel_stroke = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_stroke_du,
        metrics,
    )
    cancel_icon = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_icon_du,
        metrics,
    )
    cancel_bg = _CANCEL_BG_HOVER if is_cancel_hovered else _CANCEL_BG
    painter.setPen(QPen(_CANCEL_BORDER, cancel_stroke))
    painter.setBrush(cancel_bg)
    painter.drawEllipse(cancel_rect)

    painter.setPen(QPen(_CANCEL_ICON, cancel_stroke))
    center = cancel_rect.center()
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() - cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() + cancel_icon),
    )
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() + cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() - cancel_icon),
    )


def build_ui_overlay_image(widget, metrics) -> QImage | None:
    state = widget.runtime_state
    width = int(widget.width())
    height = int(widget.height())
    if width <= 0 or height <= 0:
        return None
    if not state._paste_overlay_visible:
        return None

    dpr = max(1.0, float(widget.devicePixelRatioF()))
    image = new_overlay_image(
        max(1, int(round(width * dpr))), max(1, int(round(height * dpr)))
    )
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(dpr, dpr)
        _draw_paste_overlay(painter, widget, metrics)
    finally:
        painter.end()
    return image
