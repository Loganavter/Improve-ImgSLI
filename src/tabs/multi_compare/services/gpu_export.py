"""Offscreen GPU exporter for the Multi Compare view.

Mirrors the main-compare path (:class:`GpuExportProxy`): a hidden
``MultiCompareCanvasWidget`` is resized to the chosen output size, the
composition tree is applied via ``apply_canvas_render_plan`` (which stashes a
``ResolvedComposition`` on the widget for ``render()`` to consume), and
``grabFramebuffer`` performs a synchronous render.

The composition is the **only** input to the renderer — no ``set_state``
shortcut, no parallel ``MultiCompareState`` mutation path. This is what makes
live and export look the same: both paths render the same canvas-px scene with
``sr = min(fb/canvas)`` applied once at draw time.
"""

from __future__ import annotations

import dataclasses
import logging

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from shared.rendering.export_tiling import (
    DEFAULT_EXPORT_TILE_MAX_EXTENT,
    TiledFramebufferExporter,
)
from shared.rendering.offscreen_canvas import (
    configure_offscreen_widget,
    render_widget_frame,
    resize_offscreen_widget,
    show_offscreen_widget,
    shutdown_offscreen_widget,
)
from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget
from ui.canvas_presentation.composition import CompositionPlan
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareGpuExporter:
    def __init__(self) -> None:
        self._widget: MultiCompareCanvasWidget | None = None
        self._last_size: tuple[int, int] | None = None

    def _ensure_widget(self) -> MultiCompareCanvasWidget:
        if self._widget is not None:
            return self._widget
        widget = MultiCompareCanvasWidget()
        widget.setObjectName("multi_compare_export_canvas")
        configure_offscreen_widget(widget)
        widget._allow_transparent_clear = True
        show_offscreen_widget(widget)
        self._widget = widget
        return widget

    def shutdown(self) -> None:
        widget = self._widget
        self._widget = None
        self._last_size = None
        shutdown_offscreen_widget(widget)

    def _apply_composition(
        self,
        widget: MultiCompareCanvasWidget,
        composition: CompositionPlan,
        *,
        background_color: QColor | None,
        fill_background: bool,
    ) -> CompositionPlan:
        if fill_background and background_color is not None:
            widget._theme_background_color = QColor(background_color)
        else:
            widget._theme_background_color = QColor(0, 0, 0, 0)

        export_fill_rgba = (
            (
                background_color.red(),
                background_color.green(),
                background_color.blue(),
                background_color.alpha(),
            )
            if fill_background and background_color is not None
            else None
        )
        composition_for_export = dataclasses.replace(
            composition, fill_rgba=export_fill_rgba
        )
        render_plan = CanvasRenderPlan(
            image1=None,
            image2=None,
            source_image1=None,
            source_image2=None,
            source_key=(),
            canvas_w=composition.canvas_w,
            canvas_h=composition.canvas_h,
            render_scene=None,
            overlay_layout=None,
            capture_visible=False,
            capture_color=QColor(0, 0, 0, 0),
            guides_enabled=False,
            guides_color=QColor(0, 0, 0, 0),
            guides_thickness=0,
            fill_rgba=export_fill_rgba,
            composition_root=composition_for_export.root,
            composition_plan=composition_for_export,
        )
        apply_canvas_render_plan(widget, render_plan)
        return composition_for_export

    def render_to_qimage(
        self,
        composition: CompositionPlan,
        *,
        output_w: int,
        output_h: int,
        background_color: QColor | None,
        fill_background: bool,
    ) -> QImage:
        """Render ``composition`` into a QImage of ``output_w`` × ``output_h``."""
        from ui.widgets.canvas.rhi_backend import query_max_texture_size

        widget = self._ensure_widget()
        output_w = max(1, int(output_w))
        output_h = max(1, int(output_h))
        target_size = (output_w, output_h)

        def prepare_frame():
            self._apply_composition(
                widget,
                composition,
                background_color=background_color,
                fill_background=fill_background,
            )
            widget._mc_overlay_debug = True
            widget.update()
            QApplication.processEvents()
            widget._mc_overlay_debug = False

        def set_export_viewport(viewport):
            widget._export_canvas_viewport = viewport

        tile_extent = min(
            DEFAULT_EXPORT_TILE_MAX_EXTENT,
            query_max_texture_size(widget.rhi()) if widget.rhi() else DEFAULT_EXPORT_TILE_MAX_EXTENT,
        )
        if output_w <= tile_extent and output_h <= tile_extent:
            set_export_viewport(None)
            if self._last_size != target_size:
                resize_offscreen_widget(widget, target_size)
                show_offscreen_widget(widget)
                self._last_size = target_size
            prepare_frame()
            render_widget_frame(widget)
            render_widget_frame(widget)
            image = widget.grabFramebuffer()
            if (image.width(), image.height()) != target_size:
                from PySide6.QtCore import Qt

                image = image.scaled(
                    target_size[0],
                    target_size[1],
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return image

        exporter = TiledFramebufferExporter(
            widget,
            set_export_viewport=set_export_viewport,
            prepare_frame=prepare_frame,
            query_max_texture_size=lambda: query_max_texture_size(widget.rhi()),
        )
        pil_image = exporter.render_rgba(
            output_w, output_h, max_extent=DEFAULT_EXPORT_TILE_MAX_EXTENT
        )
        self._last_size = exporter._last_size
        return QImage(
            pil_image.tobytes(),
            pil_image.width,
            pil_image.height,
            pil_image.width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
