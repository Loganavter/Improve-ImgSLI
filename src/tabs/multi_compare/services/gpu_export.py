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

from engine.gpu.export_tiling import (
    DEFAULT_EXPORT_TILE_MAX_EXTENT,
    TiledFramebufferExporter,
)
from engine.cache.draw_plans import plan_tiles_for_grid
from engine.cache.tile_texture_service import TileTextureService
from engine.gpu.offscreen_canvas import (
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


# ---------------------------------------------------------------------------
# MC export per-slot tile enumeration (task-engine-next-migration-2026-09-16,
# Phase S-c, S4). S0 verdict (proven, not assumed): MC export builds no plan
# object of its own -- ``save_composite`` (services/image_export.py) is pure
# PIL encode and this exporter wraps the caller-supplied ``CompositionPlan``
# built upstream by the single-owner shared live/export constructor
# (services/composition_builder.py, boundary-pinned, NOT touched here); per-slot tile enumeration already lives in
# ``scene/tile_geometry.py`` (S2/S5 scope, engine-pattern-owned) and export
# framebuffer tiling parity is already by construction
# (``TiledFramebufferExporter`` + ``offscreen_canvas``, both engine-owned).
#
# ``resolve_mc_export_slot_tiles`` is therefore the S3-mirror single
# engine-backed entry the export side exercises per render: every layer's
# whole-image tile set enumerated through the R4 vocabulary
# (``engine.cache.draw_plans.plan_tiles_for_grid``) instead of a tab-local
# decision. PERMANENT SEAM (task-engine-leftovers-2026-09-16, Phase R-d,
# ruling 4): the export GPU render re-resolves residency at render time
# through the shared live renderer (``BaseImagesPass`` + ``tile_geometry``
# adapters), so this result records the decision only; it never alters the
# render below.
#
# R4 consumption verdict (pinned, not tripwire): feeding this probe into the
# export first frame is infeasible without live-path changes, which are out
# of scope (scene/passes/* read-only). Blocking call chain:
# - The probe registers each layer's WHOLE-image set per layer_id into its
#   OWN throwaway TileTextureService; the export offscreen widget owns a
#   DIFFERENT tile_service whose specs build viewport-driven per slot via
#   build_slot_specs from the tab geometry/LOD model -- disjoint service
#   objects, and whole-image sets would additionally OVERRIDE viewport
#   culling (wrong: live culls per viewport through build_slot_plan_tiles).
# - the two residency.realize(...) entry points
#   (tabs/multi_compare/scene/passes/residency.py:548,690) take no
#   authoritative-tile parameter; the feed half flows through the merged
#   engine pass (EngineBaseImagesPass.realize) over frame.resolve_specs --
#   plumbing an authoritative set needs a new param through _SlotSpecFrame
#   + the engine realize loop.
# Equality evidence (not assumed): the S3-mirror entry uses the same
# plan_tiles_for_grid core the live path enumerates through, and
# test_live_export_parity.py pins probe==live for that core. No second
# implementations (ruling 2): this module defines no tile math of its own
# (size adaptation only -- no coverage/geometry/LOD decisions).
# ---------------------------------------------------------------------------


def _export_layer_size(image: object) -> tuple[int, int] | None:
    """Pixel size of one composition layer image (pure adaptation, no math).

    ``TiledPixelStore`` / PIL expose ``.size`` as a ``(w, h)`` tuple;
    ``QImage`` exposes callable ``width()``/``height()``; numpy arrays
    expose ``.shape``. Anything else (imageless leaf, unknown type) yields
    ``None`` and is skipped -- mirroring the composition constructor's
    imageless-leaf policy (skip, never placeholder).
    """
    size = getattr(image, "size", None)
    if isinstance(size, (tuple, list)) and len(size) == 2:
        width, height = int(size[0]), int(size[1])
        if width > 0 and height > 0:
            return (width, height)
        return None
    width_getter = getattr(image, "width", None)
    height_getter = getattr(image, "height", None)
    if callable(width_getter) and callable(height_getter):
        try:
            width, height = int(width_getter()), int(height_getter())
        except Exception:
            return None
        if width > 0 and height > 0:
            return (width, height)
        return None
    shape = getattr(image, "shape", None)
    if shape is not None and len(shape) >= 2:
        height, width = int(shape[0]), int(shape[1])
        if width > 0 and height > 0:
            return (width, height)
    return None


def _iter_export_layers(node: object):
    """Yield every ``LayerNode`` in a composition tree (any nesting)."""
    from ui.canvas_presentation.composition import LayerNode

    stack = [node]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        if isinstance(current, LayerNode):
            yield current
            continue
        children = getattr(current, "children", ())
        stack.extend(children)


def resolve_mc_export_slot_tiles(
    composition: CompositionPlan,
    *,
    tile_service: TileTextureService | None = None,
) -> dict[int, tuple[tuple[int, int], ...]]:
    """Decide per-slot tile sets for one MC export render (engine-backed).

    Every layer's *whole-image* tile set -- export renders the full
    composition, so each slot is fully visible and the visible rect is the
    whole source image (no viewport/pan/fit/zoom derivation here; the live
    renderer's viewport-driven ``build_slot_plan_tiles`` path owns that).
    Sources are registered into ``tile_service`` (a fresh
    ``TileTextureService`` when omitted) under their ``layer_id`` and
    enumerated through ``plan_tiles_for_grid`` -- the same R4 vocabulary
    S3's ``resolve_export_snapshot_lod_tiles`` core uses. Returns
    ``{layer_id: sorted tile indices}``; layers without a usable image are
    skipped (imageless-leaf policy).
    """
    service = tile_service if tile_service is not None else TileTextureService()
    tile_sets: dict[int, tuple[tuple[int, int], ...]] = {}
    for layer in _iter_export_layers(composition.root):
        size = _export_layer_size(layer.image)
        if size is None:
            continue
        width, height = size
        service.register_source(int(layer.layer_id), (width, height))
        tiles = plan_tiles_for_grid(
            service, int(layer.layer_id), (0.0, 0.0, float(width), float(height))
        )
        tile_sets[int(layer.layer_id)] = tuple(
            sorted(tile.index for tile in tiles)
        )
    return tile_sets


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
        from ui.canvas_infra.rhi.rhi_backend import query_max_texture_size

        # S4 (Phase S-c) + R4 permanent seam (see module header): export
        # per-slot tile decisions come from the R4 engine vocabulary by
        # construction -- resolve this render's tile sets through the same
        # engine-backed entry the contract pins. Record only; never alters
        # the render below (consumption infeasible per header chain).
        _export_tile_probe = resolve_mc_export_slot_tiles(composition)
        logger.debug(
            "mc export slot tile probe slots=%s tiles=%s",
            sorted(_export_tile_probe),
            {slot: len(tiles) for slot, tiles in _export_tile_probe.items()},
        )

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