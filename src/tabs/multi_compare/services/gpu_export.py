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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

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
        import time

        t0 = time.perf_counter()
        widget = MultiCompareCanvasWidget()
        widget.setObjectName("multi_compare_export_canvas")
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAutoFillBackground(False)
        widget._allow_transparent_clear = True
        t_show = time.perf_counter()
        widget.show()
        t_pe = time.perf_counter()
        QApplication.processEvents()
        self._widget = widget
        return widget

    def shutdown(self) -> None:
        widget = self._widget
        self._widget = None
        self._last_size = None
        if widget is None:
            return
        try:
            widget.hide()
        except Exception:
            pass
        try:
            widget.close()
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass

    def render_to_qimage(
        self,
        composition: CompositionPlan,
        *,
        output_w: int,
        output_h: int,
        background_color: QColor | None,
        fill_background: bool,
    ) -> QImage:
        """Render ``composition`` into a QImage of ``output_w`` × ``output_h``.

        The composition's own ``canvas_w/canvas_h`` is the canonical scene size.
        ``output_w/h`` is the framebuffer; ``render()`` letterboxes the scene
        into it with ``sr = min(output/canvas)``. No second resample.
        """
        import time

        t_total = time.perf_counter()
        widget = self._ensure_widget()
        target_size = (max(1, int(output_w)), max(1, int(output_h)))

        if fill_background and background_color is not None:
            widget._theme_background_color = QColor(background_color)
        else:
            widget._theme_background_color = QColor(0, 0, 0, 0)

        size_changed = self._last_size != target_size
        if size_changed:
            t0 = time.perf_counter()
            widget.resize(*target_size)
            t_pe = time.perf_counter()
            QApplication.processEvents()
            self._last_size = target_size

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
        t0 = time.perf_counter()
        apply_canvas_render_plan(widget, render_plan)

        if size_changed:
            # QRhiWidget swapchain rebuilds asynchronously after resize(); the
            # first frame painted at a new size can still target the stale
            # framebuffer. A throwaway warm-up frame here forces the resize to
            # settle before the frame we actually grab.
            widget.update()
            QApplication.processEvents()

        widget._mc_overlay_debug = True
        t0 = time.perf_counter()
        widget.update()
        t_pe = time.perf_counter()
        QApplication.processEvents()
        widget._mc_overlay_debug = False

        t0 = time.perf_counter()
        image = widget.grabFramebuffer()
        if (image.width(), image.height()) != target_size:
            image = image.scaled(
                target_size[0],
                target_size[1],
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return image
