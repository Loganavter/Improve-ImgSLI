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
from shared.rendering.image_identity import image_uid

from .._debug import rhi_render_debug
from ...render_context import build_render_runtime_context
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

# Throttle per-frame raw sources log — moved from renderer.py.
_last_renderer_sources_raw_sig: tuple | None = None


def prepare_frame(renderer, widget, command_buffer, clear_color=None) -> tuple | None:
    """Thin-owner wrapper: identical to ``RhiCanvasRenderer.render`` preamble.

    Covers target/rhi guard, ``apply_pending_uploads``, ``build_render_runtime_context``,
    ``should_draw``/``target_size``/``viewport_zoom``/``sources`` raw/pending handling
    (``renderer.py:344-512`` pre-split). Mutates ``renderer.resources.residency.last_rekeyed_keys``
    and ``renderer._lod_*`` via ``commit_lod_keys`` exactly as before.

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
        return None

    updates = renderer.rhi.nextResourceUpdateBatch()
    # Reset once per frame, not inside realize_tile_plan itself: a
    # same-slot content swap can be rekeyed either by apply_pending_uploads
    # below (RhiResources.upload_source, the eager whole-image/diff-role
    # upload path) or by realize_tile_plan further down (the lazy
    # TiledPixelStore path) -- both write into this same dict so the
    # fallback-LOD substitution below sees whichever one fired this frame.
    renderer.resources.residency.last_rekeyed_keys = {}
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
            global _last_renderer_sources_raw_sig  # type: ignore[used-before-def]
            _raw_sig = (base_image.use_hires, tuple(str(k) for k in texture_keys), tuple(image_uid(s) if s is not None else None for s in sources), tuple(type(s).__name__ if s is not None else None for s in sources))  # type: ignore[has-type]
            if _raw_sig != _last_renderer_sources_raw_sig:  # type: ignore[has-type]
                _last_renderer_sources_raw_sig = _raw_sig  # type: ignore[has-type]

                def _sz(o):
                    if o is None:
                        return None
                    try:
                        from shared.image_processing.tiled_pixel_store import (
                            pixel_source_size,
                        )

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
                    from shared.image_processing.tiled_pixel_store import (
                        pixel_source_size,
                    )

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
    # Device px per logical px: DPR in live render, 1.0 during tiled
    # export (widget is sized to the tile's pixel footprint).
    scale_px = target_size.width() / float(max(1, widget.width()))
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
