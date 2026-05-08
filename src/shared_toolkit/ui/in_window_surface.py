from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QBoxLayout, QVBoxLayout, QWidget

from shared_toolkit.ui.widgets.helpers import draw_rounded_shadow

def attach_in_window_widget(widget: QWidget, anchor: QWidget | None) -> object | None:
    from shared_toolkit.ui.overlay_layer import get_overlay_layer

    overlay_layer = get_overlay_layer(anchor)
    if overlay_layer is not None:
        overlay_layer.attach(widget)
    return overlay_layer

def create_shadow_surface(
    host: QWidget,
    *,
    shadow_radius: int,
    container_object_name: str,
    layout_cls: type[QBoxLayout] = QVBoxLayout,
    outer_margins: tuple[int, int, int, int] | None = None,
    content_margins: tuple[int, int, int, int] = (4, 4, 4, 4),
    content_spacing: int = 4,
) -> tuple[QBoxLayout, QWidget, QBoxLayout]:
    if outer_margins is None:
        outer_margins = (
            shadow_radius,
            shadow_radius,
            shadow_radius,
            shadow_radius,
        )

    main_layout = layout_cls(host)
    main_layout.setContentsMargins(*outer_margins)

    container = QWidget(host)
    container.setObjectName(container_object_name)
    container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    main_layout.addWidget(container)

    content_layout = layout_cls(container)
    content_layout.setContentsMargins(*content_margins)
    content_layout.setSpacing(content_spacing)

    return main_layout, container, content_layout

def paint_shadowed_surface(
    painter: QPainter,
    surface_rect,
    *,
    shadow_radius: int,
    corner_radius: int,
) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    draw_rounded_shadow(
        painter,
        surface_rect,
        steps=shadow_radius,
        radius=corner_radius,
    )
