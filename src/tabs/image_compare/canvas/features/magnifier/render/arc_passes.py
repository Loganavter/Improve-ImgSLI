"""Occluded-arc and hidden-selection QRhi passes for the magnifier.

Both passes draw per-primitive arc/ring uniforms through a single shared
arc shader (``_ArcItemsPass``); they differ only in which scene payload they
resolve into ``_items`` and whether the draw clips to the content scissor.
Split out of ``passes.py`` so this shared-arc-shader family lives apart from
the unrelated ``MagnifierPass`` (see ``magnifier_pass.py``).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QRhiCommandBuffer, QRhiViewport

from engine.cache.screen_projection import project_px_to_screen
from engine.overlay import (
    DiskItem,
    Rgba,
    SemanticOverlayItems,
    SemanticResolver,
    pack_arcs,
)
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
from engine.cache.stroke_geometry import shrink_screen_radius_for_stroke

from tabs.image_compare.canvas.features.magnifier.render.shader_layout import SHADER_DIR, ARC_UNIFORM_SIZE


def _project_center(widget, ctx, center) -> tuple[float, float]:
    """Canvas-px center for an arc/ring authored in widget-px.

    Render-target dims come from the widget (as the retired tab-side
    projector default did); zoom/pan come from ``ctx`` so the resolver
    stays ctx-first for its varying inputs.
    """
    return project_px_to_screen(
        center.x(),
        center.y(),
        float(widget.width()),
        float(widget.height()),
        float(ctx.zoom_level),
        float(getattr(ctx, "pan_offset_x", 0.0)),
        float(getattr(ctx, "pan_offset_y", 0.0)),
    )


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


def _resolve_occluded_capture_arcs(
    ctx,
) -> tuple[tuple[QPointF, float, float, float, bool], ...]:
    """Ctx-first geometry resolver: runtime snapshot first, scene payload fallback."""
    overlay = getattr(ctx, "feature_overlay", None)
    arcs = tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())
    if arcs:
        return tuple(arcs)
    payloads = (
        ctx.scene_frame.feature_payloads
        if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
        else {}
    )
    payload_arcs = payloads.get("occluded_capture_arcs")
    if payload_arcs:
        return tuple(payload_arcs)
    overlay = getattr(ctx, "feature_overlay", None)
    return tuple(getattr(overlay, "occluded_capture_arcs", ()) or ())


def _resolve_hidden_capture_circles(
    ctx,
) -> tuple[tuple[QPointF, float, bool], ...]:
    """Ctx-first geometry resolver: runtime snapshot first, scene payload fallback."""
    overlay = getattr(ctx, "feature_overlay", None)
    circles = tuple(getattr(overlay, "hidden_capture_circles", ()) or ())
    if circles:
        return circles
    payloads = (
        ctx.scene_frame.feature_payloads
        if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
        else {}
    )
    payload_circles = payloads.get("hidden_capture_circles")
    if payload_circles:
        return tuple(payload_circles)
    overlay = getattr(ctx, "feature_overlay", None)
    return tuple(getattr(overlay, "hidden_capture_circles", ()) or ())


def _resolve_hidden_overlay_circles(
    ctx,
) -> tuple[tuple[QPointF, float, bool], ...]:
    """Ctx-first geometry resolver: runtime snapshot first, scene payload fallback."""
    overlay = getattr(ctx, "feature_overlay", None)
    circles = tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())
    if circles:
        return circles
    payloads = (
        ctx.scene_frame.feature_payloads
        if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
        else {}
    )
    payload_circles = payloads.get("hidden_magnifier_circles")
    if payload_circles:
        return tuple(payload_circles)
    overlay = getattr(ctx, "feature_overlay", None)
    return tuple(getattr(overlay, "hidden_overlay_circles", ()) or ())


def _occluded_arcs_semantic_resolver(widget) -> SemanticResolver:
    """Ctx-first semantic resolver: ctx in, canvas-px arc items out.

    Arc decisions stay stateless (module resolvers above); this binding
    only adapts them to engine-typed items -- byte layout lives
    shell-side in ``pack_arcs``.
    """

    def resolve(ctx: Any) -> SemanticOverlayItems:
        items: list[DiskItem] = []
        line_width_px = max(1.0, float(ctx.resolved_style.annotation_arc_stroke_px))
        for arc in _resolve_occluded_capture_arcs(ctx):
            if len(arc) < 5:
                continue
            center, radius, start_deg, span_deg, is_active = arc
            if radius is None or radius <= 0 or span_deg is None or span_deg <= 0.25:
                continue
            cx, cy = _project_center(widget, ctx, center)
            scaled_radius = shrink_screen_radius_for_stroke(
                float(radius) * float(ctx.zoom_level), line_width_px
            )
            active = bool(is_active)
            color = QColor(255, 105, 170, 255 if active else 210)
            items.append(
                DiskItem(
                    cx=float(cx),
                    cy=float(cy),
                    radius=scaled_radius,
                    line_width_key="annotation_arc_stroke_px",
                    color=Rgba(
                        color.redF(), color.greenF(), color.blueF(), color.alphaF()
                    ),
                    extra=(
                        float(start_deg),
                        float(span_deg),
                        active,
                        True,
                        line_width_px,
                    ),
                )
            )
        return tuple(items)

    return resolve


def _hidden_selection_semantic_resolver(widget) -> SemanticResolver:
    """Ctx-first semantic resolver: ctx in, canvas-px selection items out.

    Circle decisions stay stateless (module resolvers above); this
    binding only adapts them to engine-typed items -- byte layout lives
    shell-side in ``pack_arcs``.
    """

    def resolve(ctx: Any) -> SemanticOverlayItems:
        items: list[DiskItem] = []
        stroke_px = max(1.0, float(ctx.resolved_style.annotation_selection_stroke_px))

        def _emit(center, radius, *, active: bool, capture: bool) -> None:
            if center is None or radius is None or radius <= 0:
                return
            scaled_radius = float(radius) * float(ctx.zoom_level)
            if capture:
                # Only the capture-region selection ring is clamped to touch
                # the image edge exactly; the magnifier-bubble selection
                # ring isn't, so it doesn't need the stroke-overshoot
                # correction.
                scaled_radius = shrink_screen_radius_for_stroke(
                    scaled_radius, stroke_px
                )
            if scaled_radius <= 0:
                return
            cx, cy = _project_center(widget, ctx, center)
            color = (
                QColor(255, 105, 170, 255 if active else 210)
                if capture
                else QColor(70, 190, 255, 255 if active else 210)
            )
            items.append(
                DiskItem(
                    cx=float(cx),
                    cy=float(cy),
                    radius=scaled_radius,
                    line_width_key="annotation_selection_stroke_px",
                    color=Rgba(
                        color.redF(), color.greenF(), color.blueF(), color.alphaF()
                    ),
                    extra=(0.0, 360.0, bool(active), bool(capture), stroke_px),
                )
            )

        for center, radius, is_active in _resolve_hidden_capture_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=True)
        for center, radius, is_active in _resolve_hidden_overlay_circles(ctx):
            _emit(center, radius, active=bool(is_active), capture=False)
        return tuple(items)

    return resolve


class OccludedArcPass(_ArcItemsPass):
    """Draws the occluded arc segments of the capture ring when dragging."""

    stack_role = CanvasStackRole.ANNOTATION_BORDER
    visibility = SceneVisibility.INTERACTIVE
    use_scissor = True

    @staticmethod
    def _resolve_occluded_capture_arcs(
        ctx,
    ) -> tuple[tuple[QPointF, float, float, float, bool], ...]:
        # Stateless decision layer (module resolver above); this shim
        # preserves the historical return shape (see
        # test_runtime_overlay_snapshot_contracts.py).
        return _resolve_occluded_capture_arcs(ctx)

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_occluded_capture_arcs(ctx))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        items = _occluded_arcs_semantic_resolver(widget)(ctx)
        self._items = list(
            pack_arcs(items, matrix, float(ctx.width), float(ctx.height))
        )
        self._upload_items(resource_updates)


class HiddenSelectionPass(_ArcItemsPass):
    """Selection rings for hidden capture & magnifier circles."""

    stack_role = CanvasStackRole.DEBUG_VIS
    visibility = SceneVisibility.INTERACTIVE

    @staticmethod
    def _resolve_hidden_capture_circles(
        ctx,
    ) -> tuple[tuple[QPointF, float, bool], ...]:
        # Stateless decision layer (module resolver above); this shim
        # preserves the historical return shape (see
        # test_runtime_overlay_snapshot_contracts.py).
        return _resolve_hidden_capture_circles(ctx)

    @staticmethod
    def _resolve_hidden_overlay_circles(
        ctx,
    ) -> tuple[tuple[QPointF, float, bool], ...]:
        # Stateless decision layer (module resolver above); this shim
        # preserves the historical return shape (see
        # test_runtime_overlay_snapshot_contracts.py).
        return _resolve_hidden_overlay_circles(ctx)

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
        items = _hidden_selection_semantic_resolver(widget)(ctx)
        self._items = list(
            pack_arcs(items, matrix, float(ctx.width), float(ctx.height))
        )
        self._upload_items(resource_updates)
