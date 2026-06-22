"""Offscreen GPU renderer for the Multi Compare export path.

Mirrors the live ``GLGridWidget`` pipeline so saved compositions match the
on-screen render exactly (shader-side resample, overlay text, focus/zoom/pan
state, fit-aware crop). This replaced the previous CPU ``QPainter.drawImage``
``_compose_image`` path which approximated the layout but used Qt's bilinear
``SmoothPixmapTransform`` and produced visibly different output from the live
view, especially under upscale.

The exporter owns a hidden ``GLGridWidget`` (one per controller); successive
exports reuse it and its cached slot textures, so only the first call pays the
RHI-init + texture-upload cost.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from tabs.multi_compare.ui.gl_grid import GLGridWidget
from ui.canvas_presentation.composition import CompositionPlan
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareGpuExporter:
    def __init__(self) -> None:
        self._widget: GLGridWidget | None = None
        self._last_size: tuple[int, int] | None = None

    def _ensure_widget(self) -> GLGridWidget:
        if self._widget is not None:
            return self._widget
        widget = GLGridWidget()
        widget.setObjectName("multi_compare_export_canvas")
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAutoFillBackground(False)
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
        state,
        *,
        background_color: QColor | None,
        fill_background: bool,
    ) -> QImage:
        """Render a multi-compare frame from a composition plan.

        The composition plan is the canonical description of the frame —
        it owns the canvas size and the layer tree. ``state`` is still required
        because the current renderer (a hidden ``GLGridWidget``) reads slot
        images and zoom/pan from the state object; this parameter goes away
        when the renderer becomes composition-native.
        """
        widget = self._ensure_widget()
        target_size = (
            max(1, int(composition.canvas_w)),
            max(1, int(composition.canvas_h)),
        )

        # Clear color must be assigned before render() reads it via
        # _theme_or_palette_bg(). Transparent fill goes through the alpha
        # channel of the framebuffer (widget has WA_TranslucentBackground).
        if fill_background and background_color is not None:
            widget._theme_background_color = QColor(background_color)
        else:
            widget._theme_background_color = QColor(0, 0, 0, 0)

        if self._last_size != target_size:
            widget.resize(*target_size)
            QApplication.processEvents()
            self._last_size = target_size

        # Unified entry point: the same applicator main compare uses for its
        # plan-based path. It resolves the composition tree and stashes it on
        # the widget as ``_active_composition``, then we drive the legacy
        # ``set_state`` path so the existing GLGridWidget shaders pick it up.
        # Once the renderer is composition-native this set_state goes away.
        render_plan = CanvasRenderPlan(
            image1=None,
            image2=None,
            source_image1=None,
            source_image2=None,
            source_key=(),
            canvas_w=target_size[0],
            canvas_h=target_size[1],
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
        widget.set_state(state)

        widget.update()
        QApplication.processEvents()

        result = widget.grabFramebuffer()
        # DPR on offscreen widgets typically resolves to the primary screen's
        # ratio, so the framebuffer may come out larger than the logical
        # widget size. Normalize once if needed.
        if (result.width(), result.height()) != target_size:
            result = result.scaled(
                target_size[0],
                target_size[1],
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return result
