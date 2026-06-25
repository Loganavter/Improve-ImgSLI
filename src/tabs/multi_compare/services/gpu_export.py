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
        widget = MultiCompareCanvasWidget()
        widget.setObjectName("multi_compare_export_canvas")
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAutoFillBackground(False)
        widget._allow_transparent_clear = True
        widget.show()
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
        widget = self._ensure_widget()
        target_size = (max(1, int(output_w)), max(1, int(output_h)))

        # Clear color must be assigned before render() reads it via
        # _theme_or_palette_bg(). Transparent fill uses the framebuffer alpha
        # channel (widget has WA_TranslucentBackground).
        if fill_background and background_color is not None:
            widget._theme_background_color = QColor(background_color)
        else:
            widget._theme_background_color = QColor(0, 0, 0, 0)

        if self._last_size != target_size:
            widget.resize(*target_size)
            QApplication.processEvents()
            self._last_size = target_size

        render_plan = CanvasRenderPlan(
            image1=None,
            image2=None,
            source_image1=None,
            source_image2=None,
            source_key=(),
            canvas_w=composition.canvas_w,
            canvas_h=composition.canvas_h,
            gl_scene=None,
            overlay_layout=None,
            capture_visible=False,
            capture_color=QColor(0, 0, 0, 0),
            guides_enabled=False,
            guides_color=QColor(0, 0, 0, 0),
            guides_thickness=0,
            fill_rgba=(
                (background_color.red(), background_color.green(),
                 background_color.blue(), background_color.alpha())
                if fill_background and background_color is not None
                else None
            ),
            composition_root=composition.root,
        )
        apply_canvas_render_plan(widget, render_plan)

        widget.update()
        QApplication.processEvents()
        return widget.grabFramebuffer()
