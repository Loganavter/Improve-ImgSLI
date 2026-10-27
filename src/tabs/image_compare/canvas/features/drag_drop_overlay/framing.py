"""Frame framing for the drag_drop_overlay pass: device-px size + clip matrix.

The 2026-10-27 owner report ("the drop zone's text/preview reads mirrored,
and the zone gets *smaller* at a larger interface scale") came from two frame
conventions answered in the wrong place. Both now live here, once:

* ``framebuffer_size`` — how many DEVICE pixels the frame is. image_compare's
  render context carries *logical* ``width/height`` only
  (``canvas/render_context.py`` ``ViewportContext``), so a viewport sized from
  the context draws the device-px raster into ``1/DPR`` of the framebuffer per
  axis (a quarter of the area at DPR=2). The raster and the draw viewport both
  take their size from this one function, so they cannot disagree.
* ``clip_matrix`` — where raster row 0 lands. The shell's quad maps ``v == 0``
  to clip ``y = +1`` (``engine/overlay/shell.py`` ``FULLSCREEN_VERTICES``), and
  whether ``+1`` is the top of the framebuffer is a backend convention. The
  correction comes from ``engine/gpu/rt_y_orientation`` — never decided
  locally, and never "fixed" by reversing raster rows.

Split out of ``passes.py`` (file-size policy: one QRhi pass + its resource
lifecycle there, frame math here). Pure functions, no GPU objects, so the
conventions are testable without a window.
"""

from __future__ import annotations

from engine.gpu.rt_y_orientation import composited_clip_correction

#: Used only before mounting (no RHI to ask for the backend correction). Never
#: a substitute for ``composited_clip_correction`` on a live pass.
IDENTITY_MATRIX: tuple[float, ...] = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def framebuffer_size(host, ctx) -> tuple[int, int]:
    """Framebuffer size in DEVICE pixels — the single DPR answer for the pass.

    Preference order: ``ctx.framebuffer_size`` when the context carries it (the
    engine seam, e.g. multi_compare), else the render target's own pixel size
    (the truth for a ``QRhiWidget``), else logical width/height scaled by DPR.
    """
    fb = getattr(ctx, "framebuffer_size", None)
    if fb is not None:
        try:
            fb_w, fb_h = int(round(float(fb[0]))), int(round(float(fb[1])))
        except (TypeError, ValueError, IndexError):
            fb_w = fb_h = 0
        if fb_w > 0 and fb_h > 0:
            return fb_w, fb_h
    try:
        target = host.renderTarget() if host is not None else None
        size = target.pixelSize() if target is not None else None
        if size is not None and int(size.width()) > 0 and int(size.height()) > 0:
            return int(size.width()), int(size.height())
    except Exception:
        pass
    width = int(getattr(ctx, "width", 0) or getattr(host, "width", lambda: 0)() or 800)
    height = int(getattr(ctx, "height", 0) or getattr(host, "height", lambda: 0)() or 600)
    try:
        dpr = float(host.devicePixelRatioF())
    except Exception:
        dpr = 1.0
    dpr = max(1.0, dpr)
    return (
        int(max(1, round(width * dpr))),
        int(max(1, round(height * dpr))),
    )


def clip_matrix(ctx, rhi) -> tuple[float, ...]:
    """Clip-space correction for the fullscreen quad.

    ``ctx.clip_matrix`` when the context carries a usable one (the engine
    seam); image_compare's context does not, and its canvas composites this
    pass's own render target, so the correction comes from
    ``engine/gpu/rt_y_orientation.composited_clip_correction`` — the same
    source ``engine/overlay/shell.py``'s ``clip_matrix()`` and the
    guides/capture/divider/filename passes use. Identity is reachable only
    before mounting, when there is no RHI to ask (and is what a y-up NDC
    backend needs anyway).
    """
    matrix = getattr(ctx, "clip_matrix", None)
    if matrix is not None:
        try:
            values = tuple(float(value) for value in matrix)
        except (TypeError, ValueError):
            values = ()
        if len(values) == 16:
            return values
    if rhi is None:
        return IDENTITY_MATRIX
    return composited_clip_correction(rhi)


def logical_to_framebuffer_scale(host, fb_w: int, fb_h: int) -> float:
    """Design-px -> raster-px scale: the framebuffer's own ratio, not a guess.

    ``paint_drag_drop_overlay`` works in widget logical coordinates and the
    raster is the framebuffer, so the painter scale is *derived* from the size
    ``framebuffer_size`` resolved (DPR therefore enters the raster exactly
    once, via the framebuffer size, and the tiles always fill it). Equals
    ``devicePixelRatioF()`` for a ``QRhiWidget`` target; falls back to it when
    the logical size is unknown.
    """
    try:
        logical_w = float(host.width())
    except Exception:
        logical_w = 0.0
    if logical_w > 0.0:
        return float(fb_w) / logical_w
    try:
        return max(1.0, float(host.devicePixelRatioF()))
    except Exception:
        return 1.0
