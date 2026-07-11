"""Occluded-arc and hidden-selection QRhi passes for the magnifier.

Both passes draw per-primitive arc/ring uniforms through a single shared
arc shader (``_ArcItemsPass``); they differ only in which scene payload they
resolve into ``_items`` and whether the draw clips to the content scissor.
Split out of ``passes.py`` so this shared-arc-shader family lives apart from
the unrelated ``MagnifierPass`` (see ``magnifier_pass.py``).
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QRhiCommandBuffer, QRhiViewport

from tabs.image_compare.canvas.rhi_feature_common import (
    FullscreenUniformPassResources,
    resolve_rhi_scissor,
)
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.canvas.render_common import widget_px_to_screen_px

from tabs.image_compare.canvas.features.magnifier.render.passes_common import pack_arc_uniform
from tabs.image_compare.canvas.features.magnifier.render.shader_layout import SHADER_DIR, ARC_UNIFORM_SIZE


class _ArcItemsPass(CanvasRenderPass):
    """Shared resource lifecycle + draw loop for the two arc-uniform passes.

    ``OccludedArcPass`` and ``HiddenSelectionPass`` differ only in which
    scene payload they resolve into ``_items`` (occluded capture-ring arcs
    vs. hidden-circle selection rings) and in whether the draw is clipped to
    the content scissor — everything else (buffer/pipeline lifecycle, the
    uniform-upload tail of ``prepare``, the draw loop) is identical and lives
    here once.
    """

    use_scissor = False

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(ARC_UNIFORM_SIZE)
        self._items: list[bytes] = []

    def initialize(self, rhi, target) -> None:
        self.resources.initialize(rhi, target, SHADER_DIR, "arc")

    def _upload_items(self, resource_updates) -> None:
        self.resources.ensure_items(len(self._items))
        self.resources.prepare_vertex_buffer(resource_updates)
        for index, block in enumerate(self._items):
            resource_updates.updateDynamicBuffer(
                self.resources.uniform_buffers[index], 0, block
            )

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if not self._items:
            return
        command_buffer.setGraphicsPipeline(self.resources.pipeline)
        target_size = widget.renderTarget().pixelSize()
        command_buffer.setViewport(
            QRhiViewport(
                0.0, 0.0, float(target_size.width()), float(target_size.height())
            )
        )
        if self.use_scissor:
            command_buffer.setScissor(
                resolve_rhi_scissor(
                    widget,
                    self.resources.rhi,
                    ctx,
                    clip_to_content=bool(
                        getattr(
                            widget.runtime_state,
                            "_clip_overlays_to_content_rect",
                            False,
                        )
                    ),
                )
            )
        command_buffer.setVertexInput(0, [(self.resources.vertex_buffer, 0)])
        for index in range(len(self._items)):
            command_buffer.setShaderResources(self.resources.srbs[index])
            command_buffer.draw(4)

    def release(self) -> None:
        self.resources.release()
        self._items = []


class OccludedArcPass(_ArcItemsPass):
    """Draws the occluded arc segments of the capture ring when dragging."""

    stack_role = CanvasStackRole.ANNOTATION_BORDER
    visibility = SceneVisibility.INTERACTIVE
    use_scissor = True

    @staticmethod
    def _resolve_occluded_capture_arcs(ctx) -> tuple[object, ...]:
        overlay = getattr(ctx, "feature_overlay", None)
        arcs = tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())
        if arcs:
            return arcs
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        arcs = payloads.get("occluded_capture_arcs")
        if arcs:
            return tuple(arcs)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_occluded_capture_arcs(ctx))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        line_width_px = max(1.0, float(ctx.resolved_style.annotation_arc_stroke_px))
        for arc in self._resolve_occluded_capture_arcs(ctx):
            if len(arc) < 5:
                continue
            center, radius, start_deg, span_deg, is_active = arc
            if radius is None or radius <= 0 or span_deg is None or span_deg <= 0.25:
                continue
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            scaled_radius = float(radius) * float(ctx.zoom_level)
            color = QColor(255, 105, 170, 255 if bool(is_active) else 210)
            self._items.append(
                pack_arc_uniform(
                    matrix,
                    float(ctx.width),
                    float(ctx.height),
                    float(cx),
                    float(cy),
                    scaled_radius,
                    line_width_px,
                    float(start_deg),
                    float(span_deg),
                    color,
                )
            )
        self._upload_items(resource_updates)


class HiddenSelectionPass(_ArcItemsPass):
    """Selection rings for hidden capture & magnifier circles."""

    stack_role = CanvasStackRole.DEBUG_VIS
    visibility = SceneVisibility.INTERACTIVE

    @staticmethod
    def _resolve_hidden_capture_circles(ctx) -> tuple[object, ...]:
        overlay = getattr(ctx, "feature_overlay", None)
        circles = tuple(getattr(overlay, "hidden_capture_circles", ()) or ())
        if circles:
            return circles
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_capture_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_capture_circles", ()) or ())

    @staticmethod
    def _resolve_hidden_overlay_circles(ctx) -> tuple[object, ...]:
        overlay = getattr(ctx, "feature_overlay", None)
        circles = tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())
        if circles:
            return circles
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("hidden_magnifier_circles")
        if circles:
            return tuple(circles)
        overlay = getattr(ctx, "feature_overlay", None)
        return tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(
            self._resolve_hidden_capture_circles(ctx)
            or self._resolve_hidden_overlay_circles(ctx)
        )

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        stroke_px = max(1.0, float(ctx.resolved_style.annotation_selection_stroke_px))

        def _emit(center, radius, *, active: bool, capture: bool) -> None:
            if center is None or radius is None or radius <= 0:
                return
            scaled_radius = float(radius) * float(ctx.zoom_level)
            if scaled_radius <= 0:
                return
            cx, cy = widget_px_to_screen_px(widget, center.x(), center.y())
            color = (
                QColor(255, 105, 170, 255 if active else 210)
                if capture
                else QColor(70, 190, 255, 255 if active else 210)
            )
            self._items.append(
                pack_arc_uniform(
                    matrix,
                    float(ctx.width),
                    float(ctx.height),
                    float(cx),
                    float(cy),
                    scaled_radius,
                    stroke_px,
                    0.0,
                    360.0,
                    color,
                )
            )

        for center, radius, is_active in self._resolve_hidden_capture_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=True)
        for center, radius, is_active in self._resolve_hidden_overlay_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=False)

        self._upload_items(resource_updates)
