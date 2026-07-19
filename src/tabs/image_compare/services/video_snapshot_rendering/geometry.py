"""Pure geometry helpers for snapshot frame preparation."""

from __future__ import annotations

from PIL import Image

from shared.image_processing.pixel_ops.resample import write_resampled_to_store
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.canvas.presentation.plan_builder import CanvasGeometry
from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    GlobalCanvasBounds,
    VideoRenderRequest,
)

_RESAMPLE = {
    "NEAREST": Image.Resampling.NEAREST,
    "BILINEAR": Image.Resampling.BILINEAR,
    "BICUBIC": Image.Resampling.BICUBIC,
    "LANCZOS": Image.Resampling.LANCZOS,
    "EWA_LANCZOS": Image.Resampling.LANCZOS,
}


def _resample_for_method(method_name: str) -> Image.Resampling:
    return _RESAMPLE.get(str(method_name).upper(), Image.Resampling.LANCZOS)


def resolve_prescale_target(request: VideoRenderRequest) -> tuple[int, int]:
    target_w = max(1, int(request.target_surface.width))
    target_h = max(1, int(request.target_surface.height))
    bounds = request.global_bounds
    if bounds is None:
        return target_w, target_h

    span_x = max(
        1.0,
        float(getattr(bounds, "canvas_x_max", 1.0))
        - float(getattr(bounds, "canvas_x_min", 0.0)),
    )
    span_y = max(
        1.0,
        float(getattr(bounds, "canvas_y_max", 1.0))
        - float(getattr(bounds, "canvas_y_min", 0.0)),
    )
    required_base_w = max(1, int(round(float(target_w) / span_x)))
    required_base_h = max(1, int(round(float(target_h) / span_y)))
    return (
        max(target_w, required_base_w),
        max(target_h, required_base_h),
    )


def fit_source_to_content(
    source,
    content_size: tuple[int, int],
    fill_rgba: tuple[int, int, int, int] | None = None,
    resize_method: str = "LANCZOS",
):
    """Scale ``source`` to fit *inside* ``content_size`` without letterbox bake.

    Returns an unpadded ``TiledPixelStore`` (or the original when already small
    enough). Aspect letterbox margins are expressed by folding insets into
    ``CanvasGeometry`` pads — see ``geometry_with_aspect_insets``.
    ``fill_rgba`` is accepted for call-site compatibility and ignored.
    """
    del fill_rgba
    cw, ch = content_size
    sw, sh = int(source.width), int(source.height)
    if sw <= 0 or sh <= 0 or cw <= 0 or ch <= 0:
        return source

    fit_r = min(cw / max(1, sw), ch / max(1, sh), 1.0)
    tw = max(1, int(sw * fit_r))
    th = max(1, int(sh * fit_r))
    if (tw, th) == (sw, sh) and isinstance(source, TiledPixelStore):
        return source
    if (tw, th) == (sw, sh) and isinstance(source, Image.Image):
        return TiledPixelStore.from_pil(
            source if source.mode == "RGBA" else source.convert("RGBA")
        )

    resample = _resample_for_method(resize_method)
    out = TiledPixelStore.allocate(tw, th)
    write_resampled_to_store(out, source, tw, th, resample)
    return out


def geometry_with_aspect_insets(
    canvas_geometry: CanvasGeometry,
    fitted_size: tuple[int, int],
) -> CanvasGeometry:
    """Fold aspect letterbox into pads so the image fills the content box."""
    content_w = max(1, int(canvas_geometry.image_width))
    content_h = max(1, int(canvas_geometry.image_height))
    fw, fh = int(fitted_size[0]), int(fitted_size[1])
    if fw <= 0 or fh <= 0:
        return canvas_geometry
    if (fw, fh) == (content_w, content_h):
        return canvas_geometry

    inset_x = max(0, (content_w - fw) // 2)
    inset_y = max(0, (content_h - fh) // 2)
    return CanvasGeometry(
        image_width=fw,
        image_height=fh,
        canvas_width=int(canvas_geometry.canvas_width),
        canvas_height=int(canvas_geometry.canvas_height),
        padding_left=int(canvas_geometry.padding_left) + inset_x,
        padding_top=int(canvas_geometry.padding_top) + inset_y,
        padding_right=int(canvas_geometry.padding_right)
        + max(0, content_w - fw - inset_x),
        padding_bottom=int(canvas_geometry.padding_bottom)
        + max(0, content_h - fh - inset_y),
        virtual_layout=canvas_geometry.virtual_layout,
    )


def resolve_scaled_content_geometry(
    frame,
) -> tuple[tuple[int, int], tuple[int, int], int, int]:
    """Map a prepared frame to ``(canvas_size, content_size, pad_left, pad_top)``.

    ``frame.render_*`` is the letterboxed *image* box from
    ``build_render_frame_presentation``, not the export framebuffer. The
    padded canvas must stay ``frame.target`` (export resolution). Using render
    size as the canvas collapses pillar/letterbox pads; ``render_loop`` then
    stretches the short frame to the job size (4:3 sources → fat 16:9 DAR).

    With ``virtual_layout``, pads come from normalized canvas bounds (same
    target-vs-render rule — otherwise span_y shrink invents fake side chrome).
    """
    target = getattr(frame, "target", None)
    if target is not None and int(getattr(target, "width", 0) or 0) > 0:
        canvas_w = max(1, int(target.width))
        canvas_h = max(1, int(target.height))
    else:
        canvas_w = max(1, int(frame.render_width))
        canvas_h = max(1, int(frame.render_height))

    if frame.virtual_layout is None:
        content_w = max(1, int(frame.render_width))
        content_h = max(1, int(frame.render_height))
        pad_left = max(0, int(getattr(frame, "image_dest_x", 0) or 0))
        pad_top = max(0, int(getattr(frame, "image_dest_y", 0) or 0))
        # Prefer layout pads when present (same numbers as image_dest_*).
        layout = getattr(frame, "layout", None)
        if layout is not None:
            pad_left = max(0, int(getattr(layout, "content_x", pad_left) or 0))
            pad_top = max(0, int(getattr(layout, "content_y", pad_top) or 0))
            content_w = max(1, int(getattr(layout, "content_width", content_w) or content_w))
            content_h = max(1, int(getattr(layout, "content_height", content_h) or content_h))
        return (
            (canvas_w, canvas_h),
            (content_w, content_h),
            pad_left,
            pad_top,
        )

    bounds = frame.virtual_layout.canvas_bounds
    span_x = max(1e-6, float(bounds.x_max - bounds.x_min))
    span_y = max(1e-6, float(bounds.y_max - bounds.y_min))
    base_w = max(1, int(round(canvas_w / span_x)))
    base_h = max(1, int(round(canvas_h / span_y)))
    pad_left = max(0, int(round(-float(bounds.x_min) * base_w)))
    pad_top = max(0, int(round(-float(bounds.y_min) * base_h)))
    return (
        (canvas_w, canvas_h),
        (base_w, base_h),
        pad_left,
        pad_top,
    )


def scale_global_bounds(
    bounds: GlobalCanvasBounds,
    prescale_target: tuple[int, int],
    *,
    output_size: tuple[int, int] | None = None,
) -> GlobalCanvasBounds:
    source_w = max(1, int(bounds.base_width))
    source_h = max(1, int(bounds.base_height))
    target_w, target_h = prescale_target
    ratio = min(float(target_w) / float(source_w), float(target_h) / float(source_h))
    if output_size is not None:
        out_w, out_h = output_size
        span_x = max(1.0, float(bounds.canvas_x_max) - float(bounds.canvas_x_min))
        span_y = max(1.0, float(bounds.canvas_y_max) - float(bounds.canvas_y_min))
        min_ratio = min(
            1.0,
            float(max(1, out_w)) / (float(source_w) * span_x),
            float(max(1, out_h)) / (float(source_h) * span_y),
        )
        ratio = max(ratio, min_ratio)
    if ratio >= 0.999:
        return bounds

    return GlobalCanvasBounds(
        pad_left=max(0, int(round(bounds.pad_left * ratio))),
        pad_right=max(0, int(round(bounds.pad_right * ratio))),
        pad_top=max(0, int(round(bounds.pad_top * ratio))),
        pad_bottom=max(0, int(round(bounds.pad_bottom * ratio))),
        base_width=max(1, int(round(source_w * ratio))),
        base_height=max(1, int(round(source_h * ratio))),
        canvas_x_min=float(bounds.canvas_x_min),
        canvas_x_max=float(bounds.canvas_x_max),
        canvas_y_min=float(bounds.canvas_y_min),
        canvas_y_max=float(bounds.canvas_y_max),
    )
