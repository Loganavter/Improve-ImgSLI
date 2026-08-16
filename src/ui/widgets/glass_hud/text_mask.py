"""Text-mask rasterization for ``GlassHUD`` -- split out per
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases module" pattern (own
orthogonal concern: CPU rasterization/caching of the alpha mask
``glass_composite.frag`` uses to recolor glyphs per pixel).

Functions here take the owning ``GlassHUD`` instance as their first
argument and read/write its instance state directly -- same shape as
``ui/drag_drop.py``'s split off ``MultiCompareWidget``, see that pattern's
reference table.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled

# Text color is picked *per pixel* in glass_composite.frag from that same
# pixel's own already-composited glass color, not from one flat
# per-label-average color computed here -- see
# docs/dev/rendering/glass-panel-text-vibrancy-plan.md for the full history
# (a near-opaque backing chip, then binary/continuous CPU-side average
# luminance, both tried and dropped before this). This module's only job is
# producing the alpha *mask* (where the glyphs are) the shader reads to
# know which pixels to recolor at all -- the recolor math itself (logistic
# curve, retuned from the old CPU version's constants -- see
# glass_composite.frag's comment on `steepness`) lives in the shader now.
_TEXT_MASK_UPDATE_INTERVAL_S = 0.15

# `rebuild_text_mask()` rasterizes at this multiple of the panel's own
# device resolution and uploads the mask *at that oversized resolution*,
# uncompressed -- no CPU downscale step at all (see that function's
# docstring for why: a CPU downscale, whether Qt's own SmoothTransformation
# or a PIL LANCZOS round-trip, was real, measurable per-call cost on a path
# that runs several times/sec). The GPU does the downscale instead, via a
# dedicated Lanczos-2 fragment pass (`glass_panel.py`'s `_ensure_panel`
# creates `text_mask_downsampled_tex` at the panel's own device resolution
# and a pipeline that resolves `text_mask_tex` down into it, run from
# `render_backdrops()` right after each upload) -- `glass_composite.frag`
# then samples that already-downsampled texture directly. An earlier
# version used QRhi's hardware `generateMips()` (box filter per level) plus
# `textureLod()` instead of a custom pass -- dropped for reading visibly
# softer than Lanczos on a glyph mask's sharp alpha edges, see
# docs/dev/rendering/glass-panel-text-vibrancy-plan.md's bug 17.
_TEXT_MASK_SUPERSAMPLE = 4


def panel_device_size(hud) -> QSize:
    """``hud``'s own device-px size -- same rounding
    ``GlassPanelRenderer.render_backdrops`` uses to size its scratch
    textures from ``rect_logical``/``dpr`` (see ``device_rects`` there), so
    a mask built at this size maps 1:1 onto that panel's ``vUv`` space with
    no scale mismatch."""
    dpr = hud.devicePixelRatioF()
    size = hud.container.size()
    return QSize(
        max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr))
    )


def widget_local_rect(hud, widget) -> QRect:
    """``widget``'s own on-screen content rect, in ``hud.container``-local
    logical px -- the same coordinate space ``_refresh_backdrop()``
    registers ``rect_logical`` in, so this maps 1:1 (times dpr) onto a
    ``ready_images`` sprite for that same key.

    Uses ``sizeHint()``, not ``size()``: in ``content_layout``'s
    QVBoxLayout a plain ``addWidget()`` (no alignment flag) stretches the
    widget to the layout's full column width, so ``widget.size().width()``
    is the *panel's* width, not the text's. For center-aligned labels (e.g.
    ``resolution_label1/2``, see ``primitives.py``) that stretch still
    applies but the text paints in the middle of it, not at the left edge
    -- shift the sampled rect's left edge in to match, or it'd average in
    blank glass next to the actual (narrower) text."""
    local_top_left = widget.mapTo(hud.container, QPoint(0, 0))
    content_size = widget.sizeHint().boundedTo(widget.size())
    alignment = getattr(widget, "alignment", lambda: Qt.AlignmentFlag(0))()
    if alignment & Qt.AlignmentFlag.AlignHCenter:
        local_top_left.setX(
            local_top_left.x() + (widget.width() - content_size.width()) // 2
        )
    return QRect(local_top_left, content_size)


def rebuild_text_mask(hud) -> bool:
    """Rasterizes every widget registered on ``hud`` (via
    ``add_text_backing_widget``) into a single alpha mask covering the
    whole panel, in panel-local device px -- same technique
    ``features/filename_overlay/render/label_raster.py`` uses for filename
    captions (QPainter into a QImage, uploaded as a texture), just
    producing a plain alpha shape here instead of a styled, colored label:
    the shader picks the actual visible color per pixel from its own
    already-composited glass color (see
    ``docs/dev/rendering/glass-panel-text-vibrancy-plan.md`` Phase 2), the
    mask only says *where* the glyphs are.

    Only white paint (full alpha where a glyph exists) -- rgb is never
    read by the shader, only ``.a``. Gated by a cache key so an unchanged
    panel (all these labels update only when e.g. a new image loads or
    zoom changes, not every frame) skips the QPainter work and the
    eventual GPU upload it would trigger. Returns whether the mask
    actually changed."""
    if flyout_debug_enabled():
        hud._text_mask_call_count += 1
        now_report = time.monotonic()
        if now_report - hud._text_mask_call_window_start >= 1.0:
            flyout_debug(
                "%s: rebuild_text_mask() call rate self=%#x calls=%d "
                "rebuilds=%d over %.2fs",
                type(hud).__name__,
                id(hud),
                hud._text_mask_call_count,
                hud._text_mask_rebuild_count,
                now_report - hud._text_mask_call_window_start,
            )
            hud._text_mask_call_count = 0
            hud._text_mask_rebuild_count = 0
            hud._text_mask_call_window_start = now_report

    # Time-throttle FIRST, before touching any widget -- confirmed live
    # (IMGSLI_FLYOUT_DEBUG=1 call-rate counter above) that this function
    # was being *called* 100-220 times/sec per panel (way past any real
    # repaint need -- not just the PIL/LANCZOS rebuild, the call itself),
    # and the widget walk below (mapTo/sizeHint/font().key() per registered
    # widget, building the cache_key tuple) is real, non-free per-call work
    # done every single time regardless of whether a rebuild ends up
    # happening. The old ordering ran that whole walk on every one of those
    # 100-220 calls just to compute a `cache_key` that then usually got
    # thrown away by the time check right after -- reported live as a
    # persisting freeze even once the PIL rebuild itself was already
    # correctly throttled to ~6-7/sec. Checking the clock first (cheap, no
    # widget touched) skips that walk entirely on the ~95% of calls that
    # land inside the same throttle window, cutting the *attempted* work
    # rate down to roughly the actual throttle rate instead of the raw call
    # rate.
    now = time.monotonic()
    device_size = panel_device_size(hud)
    size_unchanged = device_size == hud._text_mask_device_size
    if (
        hud._text_mask_image is not None
        and size_unchanged
        and now - hud._last_text_mask_update < _TEXT_MASK_UPDATE_INTERVAL_S
    ):
        # Time-throttle only applies when the panel is still the same size
        # as whatever `_text_mask_image` was last rasterized for -- a
        # cached mask from *before* a resize/reflow (e.g. this HUD hiding
        # on a tab switch then reappearing at a different container size,
        # see MultiCompareWidget.hideEvent/showEvent) no longer matches
        # this geometry at all, and serving it anyway for up to
        # _TEXT_MASK_UPDATE_INTERVAL_S produces a panel with its glyph mask
        # sampled at the wrong scale/rect -- reported live as "only the
        # reset button renders, the zoom text doesn't" right after a tab
        # switch. A genuine size change always needs a fresh rasterize
        # regardless of how recently the last one happened.
        #
        # Deliberately not flyout_debug()-logged here: this branch is the
        # normal case at this function's documented 100-220 calls/sec (see
        # the call-rate comment above), so logging every hit reproduces the
        # exact "way past any real repaint need" log-spam problem that
        # comment describes, just in text form instead of CPU time. Use the
        # existing call-rate summary line below to see this branch's
        # overall hit rate instead.
        return False
    if flyout_debug_enabled() and not size_unchanged:
        flyout_debug(
            "%s: rebuild_text_mask() bypassing throttle: device_size changed "
            "self=%#x old=%r new=%r",
            type(hud).__name__,
            id(hud),
            hud._text_mask_device_size,
            device_size,
        )

    widget_entries = []
    skipped_invisible = []
    for widget in hud._text_backing_widgets:
        if not widget.isVisible():
            skipped_invisible.append(widget)
            continue
        rect = widget_local_rect(hud, widget)
        widget_entries.append((widget, widget.text(), rect, widget.font().key()))
    if flyout_debug_enabled() and skipped_invisible:
        flyout_debug(
            "%s: rebuild_text_mask() self=%#x skipping not-visible backing "
            "widgets=%r (text mask will have no glyphs for these)",
            type(hud).__name__,
            id(hud),
            [(type(w).__name__, w.text()) for w in skipped_invisible],
        )
    cache_key = (
        device_size.width(),
        device_size.height(),
        tuple((text, rect, font_key) for _w, text, rect, font_key in widget_entries),
    )
    if cache_key == hud._text_mask_cache_key:
        # Content genuinely unchanged -- not just "we didn't bother
        # checking" (that case already returned above) -- so this is a
        # real no-op, not something to throttle further. Also not logged,
        # same high-call-rate reasoning as the throttle branch above.
        return False
    # Reaching here: the throttle window had already elapsed *and* content
    # actually changed. Deliberately does NOT update
    # `hud._text_mask_cache_key` on the *time* early-out above: the next
    # call after the throttle window closes must still see a "changed" key
    # relative to whatever was last *actually* rendered, not silently
    # accept a skipped intermediate state as the new baseline.
    hud._text_mask_cache_key = cache_key
    hud._last_text_mask_update = now
    hud._text_mask_device_size = device_size

    # Rasterize at _TEXT_MASK_SUPERSAMPLE x the panel's own device
    # resolution and upload it *at that size, undownscaled* --
    # `glass_panel.py` resolves it down to `device_size` with a dedicated
    # Lanczos-2 GPU pass right after upload (see this module's
    # `_TEXT_MASK_SUPERSAMPLE` docstring above), so no CPU downscale step
    # happens here (a CPU round-trip -- first Qt's own
    # `SmoothTransformation`, then a PIL LANCZOS pass -- was real,
    # measurable per-call cost on a path that runs several times/sec; the
    # GPU pass does the equivalent Lanczos downsample in hardware, for
    # effectively free, only when the mask actually changes).
    #
    # The supersampling itself is still needed: HUD text is small (thin
    # 1-2px strokes at these font sizes), and QPainter's own text AA on a
    # 1x-resolution target leaves stroke-center coverage well under full
    # opacity (confirmed live: even a glyph's own true center sampled
    # ~0.33-0.40 alpha, not ~1.0 -- see
    # docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3).
    # Rasterizing oversized first means each final (post-downsample)
    # texel's alpha is a true area-coverage average over multiple
    # subpixels, both raising genuine stroke-interior coverage much closer
    # to 1.0 *and* preserving a properly gradual edge falloff.
    supersample = _TEXT_MASK_SUPERSAMPLE
    super_size = QSize(
        device_size.width() * supersample, device_size.height() * supersample
    )
    t_rasterize_start = time.perf_counter()
    image = QImage(super_size, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(0)
    dpr = hud.devicePixelRatioF()
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(dpr * supersample, dpr * supersample)
        painter.setPen(QColor(255, 255, 255, 255))
        for widget, text, rect, _font_key in widget_entries:
            painter.setFont(widget.font())
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    finally:
        painter.end()
    hud._text_mask_image = image
    t_rasterize_ms = (time.perf_counter() - t_rasterize_start) * 1000.0

    if flyout_debug_enabled():
        flyout_debug(
            "%s: rebuild_text_mask() self=%#x super_size=%r device_size=%r "
            "rasterize=%.2fms",
            type(hud).__name__,
            id(hud),
            super_size,
            device_size,
            t_rasterize_ms,
        )
        hud._text_mask_rebuild_count += 1
    return True


def maybe_update_text_mask(hud) -> None:
    # Throttling now lives inside rebuild_text_mask() itself (needed there
    # anyway so _refresh_backdrop()'s own direct call -- e.g. on every
    # ZoomIndicator.update_zoom() tick -- gets it too, not just this
    # frameSubmitted-driven path). Cheap to call every frame in the common
    # (nothing changed, or still within the throttle window) case: an
    # early cache_key or timestamp check, no QPainter/PIL work.
    if not hud._text_backing_widgets or not hud.isVisible():
        return
    if rebuild_text_mask(hud):
        hud._refresh_backdrop()