# File-Size-Exempt: single QRhi filename-overlay pass (F5 boundary verdict) —
# one shared SDF atlas plus the per-slot N-quad draw orchestration and the
# pinned verdict prose; splitting it would fragment the boundary this contract
# test measures.
from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QMatrix4x4,
    QRhiCommandBuffer,
    QRhiViewport,
)

from ui.canvas_presentation.filename_labels import (
    font_for_style,
    label_rects,
    limit_name,
    qcolor,
    snap_rect_to_pixels,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from engine.cache.uniform_layout import assert_uniform_size
from tabs.image_compare.canvas.features.filename_overlay.render.gpu_resources import (
    _UNIFORM_SIZE,
    FilenameOverlayGpuResources,
)
from tabs.image_compare.canvas.features.filename_overlay.render.text_run import (
    pack_bg_quad,
    pack_run,
)

# std140 block (32 floats) shared byte-for-byte with
# filename_overlay.vert / .frag: mat4 mvp + vec4 bgColor (premultiplied) +
# vec2 quadSizePx + vec2 pad0 + float cornerRadiusPx + float bgEnabled +
# float sdfRangePx + float pixelSize + float edgePx + float pad1 +
# vec2 pad2.
_MATRIX_UNIFORM_FMT = "<32f"
assert_uniform_size(
    _MATRIX_UNIFORM_FMT, _UNIFORM_SIZE, label="FilenameOverlayGpuResources uniform"
)


def _slot_anchor(placement: str, is_horizontal: bool, slot_index: int) -> str:
    """Which edge of the label quad the text hugs.

    Mirrors ``ui.canvas_presentation.filename_labels.label_rects``'s own
    align choice: ``edges`` pins name1 left / name2 right, ``split_line``
    flips them (labels hug the divider), horizontal centres both.
    """
    if is_horizontal:
        return "center"
    if placement == "split_line":
        return "right" if slot_index == 0 else "left"
    return "left" if slot_index == 0 else "right"


def _elide(text: str, metrics: QFontMetrics, max_width: float, anchor: str) -> str:
    """Elide toward the anchored edge: a right-anchored label keeps its tail
    (the part nearest the divider), a left-anchored one keeps its head.
    """
    if metrics.horizontalAdvance(text) <= max_width:
        return text
    mode = {
        "right": Qt.TextElideMode.ElideLeft,
        "center": Qt.TextElideMode.ElideMiddle,
    }.get(anchor, Qt.TextElideMode.ElideRight)
    return metrics.elidedText(text, mode, max(1, int(max_width)))


def _pixel_space_mvp(rhi, ctx) -> tuple[float, ...]:
    """Pixel-space (y-down, tile-local px) -> clip matrix.

    Glyph/background quads are emitted in ``ctx`` pixel space (not NDC), so the
    uniform carries the full ortho*clipCorr product rather than the bare
    ``clipSpaceCorrMatrix`` the old NDC quads used.
    """
    proj = QMatrix4x4()
    proj.ortho(0.0, float(ctx.width), float(ctx.height), 0.0, -1.0, 1.0)
    matrix = rhi.clipSpaceCorrMatrix() * proj
    return tuple(float(v) for v in matrix.data())


def _pack_label_uniform(
    mvp,
    bg_premul: tuple[float, float, float, float],
    quad_w: float,
    quad_h: float,
    corner_radius: float,
    bg_enabled: float,
    sdf_range_px: float,
    pixel_size: float,
    edge_px: float,
) -> bytes:
    values = (
        *mvp,
        bg_premul[0],
        bg_premul[1],
        bg_premul[2],
        bg_premul[3],
        float(quad_w),
        float(quad_h),
        0.0,
        0.0,
        float(corner_radius),
        float(bg_enabled),
        float(sdf_range_px),
        float(pixel_size),
        float(edge_px),
        0.0,
        0.0,
        0.0,
    )
    return struct.pack(_MATRIX_UNIFORM_FMT, *values)


class FilenameOverlayPass(CanvasRenderPass):
    """Renders filename labels as SDF glyph quads over a procedural background.

    F5 FILENAME-VERDICT: PERMANENT BOUNDARY (not a migration candidate).
    Variant C1 re-open (2026-10-06): the per-string CPU raster, the 4x
    supersample and the GPU Lanczos downsample of variant A are gone. Text is
    per-glyph quads sampling one shared signed-distance-field atlas
    (``render/glyph_atlas.py``); the rounded-rect BACKGROUND is a mode-0 quad
    drawn through the same pipeline (signed-distance rounded box in
    ``filename_overlay.frag``). A split drag changes only the packed quad
    positions -- the atlas is keyed by ``(font, pixel_size, dpr)`` and never
    re-rasterizes on a width change.

    (1) WHAT STAYS (exact GPU sites -- see the markers below):
    one shared SDF atlas texture + linear/nearest samplers
    (``ensure_atlas`` in ``render/gpu_resources.py``), a four-attribute vertex
    layout (pos / uv / color / mode+weight), per-slot growable vertex buffers
    holding the background quad plus N glyph quads, per-slot 128-byte uniform
    buffers, per-slot screen draws of N quads (``prepare`` / ``record``
    below), and per-slot ``srb_linear`` / ``srb_nearest`` selection.

    (2) WHY (uniqueness proof): N independently-positioned glyph quads sampling
    a shared atlas, plus a procedural rounded-box background composited through
    per-slot uniforms, has no image in the single-fullscreen-upload
    ``TexturedOverlayShell`` (one texture, upload-then-draw in the same main
    pass, shared ``FULLSCREEN_VERTICES``, one ``srb``, one 64B uniform). MC
    ``layer_labels`` rides the shell ONLY because it is one fullscreen raster
    with a pre-composited background.

    (3) INVALIDATION CONDITION: re-open this verdict if the shell gains a
    shared glyph atlas plus per-glyph quads, or if these labels drop the atlas
    + per-slot N-quad shape for a single fullscreen raster like MC. Moving the
    background between CPU and shader does not invalidate the verdict by
    itself. Either resource-shape change breaks the markers pinned in
    ``src/tabs/image_compare/tests/render/test_filename_boundary.py``.
    """

    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._gpu = FilenameOverlayGpuResources()

    def initialize(self, rhi, target) -> None:
        self._gpu.initialize(rhi, target)

    def should_paint(self, ctx) -> bool:
        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return False
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        if not bool(getattr(cfg, "enabled", False)) and single_preview == 0:
            return False
        images_uploaded = list(getattr(ctx, "images_uploaded", ()) or ())
        has_slot1 = bool(images_uploaded[0]) if len(images_uploaded) > 0 else False
        has_slot2 = bool(images_uploaded[1]) if len(images_uploaded) > 1 else False
        raw_name1 = str(getattr(cfg, "name1", "") or "").strip()
        raw_name2 = str(getattr(cfg, "name2", "") or "").strip()
        if single_preview == 1:
            if not has_slot1 or not raw_name1:
                return False
        elif single_preview == 2:
            if not has_slot2 or not raw_name2:
                return False
        else:
            if not (has_slot1 and has_slot2):
                return False
            if not (raw_name1 or raw_name2):
                return False
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        if render_mode == "interactive" and single_preview == 0 and zoom > 1.0 + 1e-6:
            return False
        return ctx.width > 0 and ctx.height > 0

    def prepare(self, widget, ctx, resource_updates) -> None:
        for slot in self._gpu.slots:
            slot.active = False
            slot.vertices = None
            slot.vertex_count = 0

        cfg = (
            ctx.scene_frame.feature_payloads.get("filename_overlay")
            if isinstance(ctx.scene_frame.feature_payloads, dict)
            else None
        )
        if cfg is None:
            return

        content_rect = ctx.scene_frame.image_rect_px
        if content_rect is None or content_rect[2] <= 0 or content_rect[3] <= 0:
            return

        split_override = ctx.scene_frame.split_override
        zoom = float(getattr(ctx, "zoom_level", 1.0) or 1.0)
        pan_x = float(getattr(ctx, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(ctx, "pan_offset_y", 0.0) or 0.0)
        single_preview = int(getattr(ctx.scene_frame, "single_image_preview", 0) or 0)
        render_mode = str(
            getattr(getattr(ctx, "render_metrics", None), "mode", "") or ""
        )
        is_interactive_live = render_mode == "interactive"
        image_anchored = not (single_preview != 0 and is_interactive_live)
        apply_transform = image_anchored and (
            abs(zoom - 1.0) > 1e-6 or abs(pan_x) > 1e-9 or abs(pan_y) > 1e-9
        )
        # Pivot/pan scale off the logical canvas center (== widget center
        # outside tiled export), then shift into this render target's
        # tile-local pixel space via canvas_offset_x/y so the pixel-space
        # quads (and the ortho mvp built from ctx.width/height) stay tile-local.
        canvas_w = float(ctx.canvas_width)
        canvas_h = float(ctx.canvas_height)
        wcx = canvas_w / 2.0
        wcy = canvas_h / 2.0

        def _to_screen_rect(r: QRectF) -> QRectF:
            if not apply_transform:
                left = r.left() - ctx.canvas_offset_x
                top = r.top() - ctx.canvas_offset_y
                return QRectF(left, top, r.width(), r.height())
            left = (
                wcx
                + (r.left() - wcx) * zoom
                + pan_x * canvas_w * zoom
                - ctx.canvas_offset_x
            )
            top = (
                wcy
                + (r.top() - wcy) * zoom
                + pan_y * canvas_h * zoom
                - ctx.canvas_offset_y
            )
            return QRectF(left, top, r.width() * zoom, r.height() * zoom)

        name1 = str(getattr(cfg, "name1", "") or "")
        name2 = str(getattr(cfg, "name2", "") or "")
        divider_thickness_px = float(
            (
                ctx.scene_frame.feature_payloads.get("filename_divider_thickness", 0)
                if isinstance(ctx.scene_frame.feature_payloads, dict)
                else 0
            )
            or 0
        )
        max_name_length = int(getattr(cfg, "max_name_length", 50))
        if single_preview == 1:
            name1 = limit_name(name1, max_name_length)
            name2 = ""
            split_override = 1.0
        elif single_preview == 2:
            name1 = ""
            name2 = limit_name(name2, max_name_length)
            split_override = 0.0
        else:
            name1 = limit_name(name1, max_name_length)
            name2 = limit_name(name2, max_name_length)

        overlay_style = ctx.resolved_style.filename_overlay
        font = font_for_style(widget, overlay_style)
        font_metrics = QFontMetrics(font)
        rect1, rect2 = label_rects(
            cfg,
            content_rect,
            font_metrics,
            name1,
            name2,
            overlay_style,
            split_override,
            divider_thickness_wx=divider_thickness_px,
        )
        rect1 = snap_rect_to_pixels(rect1)
        rect2 = snap_rect_to_pixels(rect2)

        text_color = qcolor(
            getattr(cfg, "file_name_color", None), QColor(255, 0, 0, 255)
        )
        raw_alpha = max(0, min(255, int(text_color.alpha() * overlay_style.text_alpha)))
        text_color.setAlpha(raw_alpha)
        bg_color = qcolor(getattr(cfg, "file_name_bg_color", None), QColor(0, 0, 0, 255))
        bg_color.setAlpha(
            max(0, min(255, int(bg_color.alpha() * overlay_style.text_alpha)))
        )
        draw_bg = bool(getattr(cfg, "draw_text_background", True))
        font_weight = int(getattr(cfg, "font_weight", 0) or 0)
        text_inset = float(overlay_style.text_inset_px)
        is_horizontal = bool(getattr(cfg, "is_horizontal", False))
        placement = str(getattr(cfg, "text_placement_mode", "edges") or "edges")

        dpr = max(1.0, float(widget.devicePixelRatioF()))
        font_px = int(round(float(overlay_style.font_pixel_size)))
        if font_px <= 0:
            font_px = max(1, int(font.pixelSize()))
        # Build/refresh the shared SDF atlas only when the font/size/dpr triple
        # changes -- a split drag never reaches the atlas (C1's core win).
        if self._gpu.ensure_atlas(font, font_px, dpr, int(font_weight)):
            if self._gpu.atlas_image is not None:
                resource_updates.uploadTexture(
                    self._gpu.atlas_texture, self._gpu.atlas_image
                )
        atlas = self._gpu.atlas
        if atlas is None:
            return

        # Premultiplied rgba, as the fragment shader outputs premultiplied.
        bg_alpha = bg_color.alphaF()
        bg_premul = (
            bg_color.redF() * bg_alpha,
            bg_color.greenF() * bg_alpha,
            bg_color.blueF() * bg_alpha,
            bg_alpha,
        )
        text_alpha_f = text_color.alphaF()
        text_premul = (
            text_color.redF() * text_alpha_f,
            text_color.greenF() * text_alpha_f,
            text_color.blueF() * text_alpha_f,
            text_alpha_f,
        )
        mvp = _pixel_space_mvp(self._gpu.rhi, ctx)
        sdf_range = float(atlas.sdf_range_px)

        for i, (name, rect) in enumerate([(name1, rect1), (name2, rect2)]):
            slot = self._gpu.slots[i]
            if not name or rect is None:
                continue
            quad_w = float(rect.width())
            quad_h = float(rect.height())
            anchor = _slot_anchor(placement, is_horizontal, i)
            max_text_w = max(1.0, quad_w - text_inset * 2.0)
            elided = _elide(name, font_metrics, max_text_w, anchor)
            text_w = max(1.0, float(font_metrics.horizontalAdvance(elided)))

            screen_rect = _to_screen_rect(rect)
            zoom_scale = (screen_rect.width() / quad_w) if quad_w > 0 else 1.0
            display_w = text_w * zoom_scale
            display_inset = text_inset * zoom_scale
            if anchor == "right":
                tx = screen_rect.width() - display_inset - display_w
            elif anchor == "center":
                tx = (screen_rect.width() - display_w) * 0.5
            else:
                tx = display_inset
            origin_x = screen_rect.left() + tx
            baseline_y = screen_rect.top() + (
                (quad_h - float(font_metrics.height())) * 0.5
                + float(font_metrics.ascent())
            ) * zoom_scale

            vertices = bytearray()
            if draw_bg:
                vertices += pack_bg_quad(
                    (
                        screen_rect.left(),
                        screen_rect.top(),
                        screen_rect.right(),
                        screen_rect.bottom(),
                    )
                )
            run, glyph_count = pack_run(
                elided,
                atlas,
                (origin_x, baseline_y),
                text_premul,
                float(font_weight),
                zoom_scale,
            )
            vertices += run
            if not vertices:
                continue

            # BOUNDARY (F5): per-slot screen quads -- the background quad plus
            # N glyph quads, each packed from text_run, never the shared
            # FULLSCREEN_VERTICES the TexturedOverlayShell stages.
            self._gpu.ensure_vertex_capacity(slot, len(vertices))
            resource_updates.updateDynamicBuffer(slot.vertex_buffer, 0, bytes(vertices))
            slot.vertices = bytes(vertices)
            slot.vertex_count = (6 if draw_bg else 0) + glyph_count * 6

            corner_radius = float(overlay_style.label_corner_radius_px) * zoom_scale * dpr
            # AA half-width: sd is in logical atlas px. Per docs/dev/rendering/
            # patterns.md ("SDF edge feather minimum"), a smoothstep SDF edge
            # under single-sample rasterization needs a feather HALF-width of
            # >= ~1px or it aliases into a hard/jagged step (the "binary alpha"
            # seen live). 1 device px = 1/(zoom_scale*dpr) logical px.
            edge_px = 1.0 / max(1e-6, zoom_scale * dpr)
            resource_updates.updateDynamicBuffer(
                slot.uniform_buffer,
                0,
                _pack_label_uniform(
                    mvp,
                    bg_premul,
                    screen_rect.width() * dpr,
                    screen_rect.height() * dpr,
                    corner_radius,
                    1.0 if draw_bg else 0.0,
                    sdf_range,
                    float(font_px),
                    edge_px,
                ),
            )
            slot.smooth = bool(apply_transform)
            slot.active = True

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if self._gpu.pipeline is None:
            return
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        fb_width = float(int(ctx.width) * dpr)
        fb_height = float(int(ctx.height) * dpr)
        command_buffer.setGraphicsPipeline(self._gpu.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_width, fb_height))
        # BOUNDARY (F5): per-slot N-quad draw -- own vertex buffer per slot plus
        # srb_linear/srb_nearest selection. The shell draws one fullscreen quad
        # through one srb; this loop cannot delegate to it.
        for slot in self._gpu.slots:
            if not slot.active or slot.vertex_count <= 0:
                continue
            # The SDF atlas MUST be sampled with the LINEAR filter: nearest
            # sampling defeats the distance-field AA (each fragment gets one
            # texel's distance, so the threshold edge is hard/jagged, and at a
            # non-1:1 scale it aliases into a mottled "fur"). The mode-0
            # background quad carries no texture, so the sampler is moot there.
            srb = slot.srb_linear
            command_buffer.setShaderResources(srb)
            command_buffer.setVertexInput(0, [(slot.vertex_buffer, 0)])
            command_buffer.draw(slot.vertex_count)

    def release(self) -> None:
        self._gpu.release()


RENDER_PASSES: list[CanvasRenderPass] = [FilenameOverlayPass()]
RENDER_PASSES = RENDER_PASSES
