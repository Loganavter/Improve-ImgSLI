# Audit-Meta: pattern=thin-owner-target size=exempt reason="frame setup extracted from RhiCanvasRenderer — see renderer.py Audit-Meta thin-owner"
"""Frame setup extracted from ``RhiCanvasRenderer`` (CODE_PATTERNS thin owner).

``RhiCanvasRenderer.render`` contained ~170 LOC of per-frame preamble
(target/rhi guard, ``apply_pending_uploads``, ``build_render_runtime_context``,
``should_draw``/``target_size``/``viewport_zoom``/``sources`` raw/pending
handling including ``resolve_lod_texture_keys`` settle via ``commit_lod_keys``).
This module holds the same body as a plain function taking the owning renderer
as first arg — the owner keeps construction/wiring + instance state
(``rhi/resources/tile_service/_last_good_*``) per CODE_PATTERNS.md:25.
"""

from __future__ import annotations

from ui.canvas_infra.rhi.render_common import should_render_blank_white
from ui.canvas_infra.rhi.render_mode import EXPORT_CANVAS_OBJECT_NAME
from engine.cache.image_identity import image_uid

from .._debug import rhi_render_debug
from ...render_context import build_render_runtime_context
from engine.frame.context import FrameContext, make_ids, viewport_hash
from tabs.image_compare.canvas.loupe_trace import throttle_emit as _throttle_emit
from ...texture_parts.tile_geometry import _viewport_zoom_offset_for_tile
from .lod_commit import commit_lod_keys

try:
    from tabs.image_compare.debug import ic_preview_debug as _ic_preview_log  # type: ignore
    from tabs.image_compare.debug import ic_preview_debug_enabled as _ic_preview_enabled  # type: ignore
except Exception:  # pragma: no cover

    def _ic_preview_log(msg: str, *args, **kwargs) -> None:  # type: ignore
        return None

    def _ic_preview_enabled() -> bool:  # type: ignore
        return False

# Throttle per-frame raw sources log — state lives in loupe_trace's
# centralized throttle store (stream "frame_setup.sources_raw").


def resolve_canvas_scale_px(widget, target_size) -> float:
    """Device px per logical px for the LOD canvas-size input.

    Live render measures the surface (``target`` vs widget width == DPR).
    Export must NOT measure the tile surface: during tiled export the
    widget is sized to one tile's footprint while the canvas stays the
    full export size, so target/widget is tile geometry, not DPR — feeding
    it into the LOD input would resolve a per-tile level (seams: all tiles
    of one export must sample one level). Export canvas px are device px by
    construction (the exporter explicitly resizes the widget in those px),
    so the multiplier is 1.0. Same objectName signal that
    ``build_render_runtime_context`` uses for its export mode
    (``EXPORT_CANVAS_OBJECT_NAME`` in ``ui/canvas_infra/rhi/render_mode.py``);
    unknown widgets fall through to the measured ratio (old behavior).
    """
    try:
        if str(widget.objectName()) == EXPORT_CANVAS_OBJECT_NAME:
            return 1.0
    except Exception:
        pass
    return target_size.width() / float(max(1, widget.width()))


def prepare_frame(
    renderer,
    widget,
    command_buffer,
    clear_color=None,
    frame_context: FrameContext | None = None,
) -> tuple | None:
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer.render`` preamble.

    Covers target/rhi guard, ``apply_pending_uploads``, ``build_render_runtime_context``,
    ``should_draw``/``target_size``/``viewport_zoom``/``sources`` raw/pending handling
    (the pre-split ``RhiCanvasRenderer.render`` preamble). Mutates ``renderer.resources.residency.last_rekeyed_keys``
    and ``renderer._lod_*`` via ``commit_lod_keys`` exactly as before.

    ``frame_context`` is the Phase-2 frame-bus hook: when provided, the two
    early-skip exits record their reason IN ADDITION to existing behavior
    (``None`` keeps every existing call site behavior-identical).

    Returns ``None`` when frame should be skipped (no target/rhi) so caller can
    ``return False``. Otherwise returns a tuple
    ``(ctx, base_image, should_draw, target_size, target, updates, viewport_zoom,
    viewport_offset, texture_keys, sources, source_changed, diff_source_key,
    sampler_name)``. When ``should_draw`` is ``False`` the last five are ``None``/
    ``False``/``None`` placeholders so the caller can still run mips/draw submit.
    """
    target = widget.renderTarget()
    if target is None or renderer.rhi is None:
        rhi_render_debug(
            "render skip widget=%s target=%r rhi=%r",
            f"{type(widget).__name__}@{id(widget):x}",
            target,
            renderer.rhi,
        )
        # Phase-2 frame bus: early-skip reason (record only, never instead).
        if frame_context is not None:
            frame_context.record(
                "prepare_frame",
                "skipped",
                "prepare_frame early-skip no-target-or-rhi"
                f" target={'set' if target is not None else 'none'}"
                f" rhi={'set' if renderer.rhi is not None else 'none'}",
                ids=make_ids(frame_context.frame_id, "no-target-or-rhi"),
            )
        return None

    updates = renderer.rhi.nextResourceUpdateBatch()
    # Reset once per frame, not inside realize_tile_plan itself: a
    # same-slot content swap can be rekeyed either by apply_pending_uploads
    # below (RhiResources.upload_source, the eager whole-image/diff-role
    # upload path) or by realize_tile_plan further down (the lazy
    # TiledPixelStore path) -- both write into this same dict so the
    # fallback-LOD substitution below sees whichever one fired this frame.
    renderer.resources.residency.last_rekeyed_keys = {}
    # Same per-frame life as the rekeyed map above: the content-identity
    # verdict ("this slot now shows a different picture") is a fact about
    # THIS frame's uploads, and the fallback decision below is the only
    # reader. Stale entries from an earlier frame would keep dropping a
    # baseline that has since become legitimate again.
    renderer.resources.residency.last_content_replaced_keys = set()
    renderer.resources.apply_pending_uploads(widget, renderer.tile_service, updates)
    ctx = build_render_runtime_context(widget)
    base_image = getattr(ctx.render_list, "base_image", None)
    should_draw = (
        base_image is not None
        and any(ctx.images_uploaded)
        and not should_render_blank_white(ctx.scene_frame)
    )
    target_size = target.pixelSize()
    if clear_color is not None:
        rhi_render_debug(
            "render begin widget=%s widget=%dx%d target_px=%dx%d clear=rgba(%d,%d,%d,%d) "
            "images=%s should_draw=%s passes=%d fixed=%dx%d",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target_size.width(),
            target_size.height(),
            clear_color.red(),
            clear_color.green(),
            clear_color.blue(),
            clear_color.alpha(),
            list(ctx.images_uploaded),
            should_draw,
            len(renderer.feature_passes),
            widget.fixedColorBufferSize().width(),
            widget.fixedColorBufferSize().height(),
        )
    else:
        rhi_render_debug(
            "render begin widget=%s widget=%dx%d target_px=%dx%d clear=rgba(%d,%d,%d,%d) "
            "images=%s should_draw=%s passes=%d fixed=%dx%d",
            f"{type(widget).__name__}@{id(widget):x}",
            widget.width(),
            widget.height(),
            target_size.width(),
            target_size.height(),
            0,
            0,
            0,
            0,
            list(ctx.images_uploaded),
            should_draw,
            len(renderer.feature_passes),
            widget.fixedColorBufferSize().width(),
            widget.fixedColorBufferSize().height(),
        )

    # Phase 3 (docs/dev/TILED_RENDERING_DESIGN.md): resolves to exactly
    # (base_image.zoom, base_image.zoom)/(pan_x, pan_y) — a no-op — when
    # ctx.canvas_* equals widget.width()/height()/0/0 (every render
    # outside tiled export). Safe to always compute and pass through.
    viewport_zoom, viewport_offset = _viewport_zoom_offset_for_tile(
        ctx.canvas_width,
        ctx.canvas_height,
        (
            ctx.canvas_offset_x,
            ctx.canvas_offset_y,
            ctx.canvas_offset_x + widget.width(),
            ctx.canvas_offset_y + widget.height(),
        ),
        base_zoom=(base_image.zoom, base_image.zoom) if base_image else (1.0, 1.0),
        base_offset=(
            (base_image.pan_offset_x, base_image.pan_offset_y)
            if base_image
            else (0.0, 0.0)
        ),
    )

    # Early out when nothing to draw — still return context for mips/draw submit
    if not should_draw:
        # Phase-2 frame bus: early-skip reason (record only, never instead).
        if frame_context is not None:
            _vhash = viewport_hash(viewport_zoom, viewport_offset)
            frame_context.record(
                "prepare_frame",
                "skipped",
                "prepare_frame early-skip should_draw=False"
                f" base_image={'set' if base_image is not None else 'none'}"
                f" uploaded={list(ctx.images_uploaded)}"
                f" viewport_hash={_vhash}",
                ids=make_ids(frame_context.frame_id, _vhash),
            )
        return (
            ctx,
            base_image,
            should_draw,
            target_size,
            target,
            updates,
            viewport_zoom,
            viewport_offset,
            None,
            None,
            False,
            None,
            None,
        )

    texture_keys = (
        tuple(ctx.source_texture_ids)
        if base_image.use_hires
        else tuple(ctx.texture_ids)
    )
    sources = (
        tuple(widget.runtime_state._source_pil_images)
        if base_image.use_hires
        else tuple(ctx.stored_pil_images)
    )
    # Gated debug: avoid 4× image_uid + type + closure alloc per frame when off
    # sources vs draw_plan stale fix: this is raw (pre-LOD) log; the
    # committed log after LOD commit below reflects what was actually drawn.
    if _ic_preview_enabled():
        # throttle: raw sources at 60Hz — emit only when sig changes
        try:
            _raw_sig = (base_image.use_hires, tuple(str(k) for k in texture_keys), tuple(image_uid(s) if s is not None else None for s in sources), tuple(type(s).__name__ if s is not None else None for s in sources))  # type: ignore[has-type]
            if _throttle_emit("frame_setup.sources_raw", _raw_sig):  # type: ignore[has-type]

                def _sz(o):
                    if o is None:
                        return None
                    try:
                        from engine.store.tiled_pixel_store import pixel_source_size

                        w, h = pixel_source_size(o)
                        if w == 0 and h == 0:
                            return None
                        return (w, h)
                    except Exception:
                        return None

                _ic_preview_log(
                    "sources raw use_hires=%s tex_keys_raw=%s src_tex_ids=%s src_uids=%s types=%s sizes=%s ids=0x%x/0x%x stored_uids=%s source_pil_uids=%s is_same_object_raw=%s",
                    base_image.use_hires,
                    list(texture_keys),
                    list(ctx.source_texture_ids),
                    [image_uid(s) if s is not None else None for s in sources],
                    [type(s).__name__ if s is not None else None for s in sources],
                    [_sz(s) for s in sources],
                    id(sources[0]) if len(sources) > 0 and sources[0] is not None else 0,
                    id(sources[1]) if len(sources) > 1 and sources[1] is not None else 0,
                    [image_uid(s) if s is not None else None for s in ctx.stored_pil_images],
                    [image_uid(s) if s is not None else None for s in getattr(widget.runtime_state, "_source_pil_images", ())],
                    (len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]),
                )
        except Exception:
            # fallback: log without throttle

            def _sz(o):
                if o is None:
                    return None
                try:
                    from engine.store.tiled_pixel_store import pixel_source_size

                    w, h = pixel_source_size(o)
                    if w == 0 and h == 0:
                        return None
                    return (w, h)
                except Exception:
                    return None

            _ic_preview_log(
                "sources raw use_hires=%s tex_keys_raw=%s src_tex_ids=%s src_uids=%s types=%s sizes=%s ids=0x%x/0x%x stored_uids=%s source_pil_uids=%s is_same_object_raw=%s",
                base_image.use_hires,
                list(texture_keys),
                list(ctx.source_texture_ids),
                [image_uid(s) if s is not None else None for s in sources],
                [type(s).__name__ if s is not None else None for s in sources],
                [_sz(s) for s in sources],
                id(sources[0]) if len(sources) > 0 and sources[0] is not None else 0,
                id(sources[1]) if len(sources) > 1 and sources[1] is not None else 0,
                [image_uid(s) if s is not None else None for s in ctx.stored_pil_images],
                [image_uid(s) if s is not None else None for s in getattr(widget.runtime_state, "_source_pil_images", ())],
                (len(sources) == 2 and sources[0] is not None and sources[0] is sources[1]),
            )
    # Device px per logical px — export pins 1.0 by construction (see
    # resolve_canvas_scale_px: the tile surface must not leak into the
    # whole-canvas LOD decision).
    scale_px = resolve_canvas_scale_px(widget, target_size)
    texture_keys, source_changed = commit_lod_keys(
        renderer,
        texture_keys,
        sources,
        base_image,
        (ctx.canvas_width * scale_px, ctx.canvas_height * scale_px),
    )
    diff_source_key = (
        ctx.diff_source_texture_id if ctx.diff_source_ready else None
    )
    sampler_name = (
        "nearest"
        if str(ctx.scene_frame.zoom_interpolation_method).upper() == "NEAREST"
        else "linear"
    )
    return (
        ctx,
        base_image,
        should_draw,
        target_size,
        target,
        updates,
        viewport_zoom,
        viewport_offset,
        texture_keys,
        sources,
        source_changed,
        diff_source_key,
        sampler_name,
    )
