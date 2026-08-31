"""Eager max envelope — single geometry owner, no hold.

Host helper (no Store import) for comparison letterbox.
Computes ``pw,ph = max(w1,w2), max(h1,h2)`` once and derives a single
``resolve_canvas_content_geometry(cw,ch,pw,ph)`` fitted rect for both sides.
Both sides receive the same ``(ux/cw, uy/ch, uw/cw, uh/ch)`` and pixel rect.
Fallback to per-image when one side has no size (``w==0`` or ``h==0``).

Used by:
- ``tabs/image_compare/canvas/texture_parts/base_images.py:196``
  ``update_common_letterbox_geometry``
- ``tabs/image_compare/presenters/image_canvas/background_parts/render_flow.py:55``
  ``_update_comparison_geometry``

Pure, no Store, no hold, no more_pending.
"""

from __future__ import annotations

from ui.canvas_infra.scene.frame_geometry import resolve_canvas_content_geometry


def eager_envelope_rect(
    cw: int,
    ch: int,
    sizes: list[tuple[int, int]],
) -> tuple[tuple[float, float, float, float], tuple[int, int, int, int]]:
    """Compute eager max envelope letterbox + pixel rect.

    Args:
        cw: canvas logical width (px).
        ch: canvas logical height (px).
        sizes: ``[(w1,h1),(w2,h2)]`` — zero means missing.

    Returns:
        ``(letterbox, content_rect)`` where
        ``letterbox = (ux/cw, uy/ch, uw/cw, uh/ch)`` normalized for both sides
        when both have sizes, or per-image when one is missing,
        ``content_rect = (x, y, w, h)`` pixel rect (rounded, ``max(1, ...)``).

        Both slots receive the same tuple when envelope applies — stable from
        first ``gap draw_plan`` (no hold).
    """
    # canvas zero guard — matches update_letterbox_geometry identity
    if cw <= 0 or ch <= 0:
        return ((0.0, 0.0, 1.0, 1.0), (0, 0, max(1, cw), max(1, ch)))

    # normalize sizes list to two entries
    w1, h1 = (0, 0)
    w2, h2 = (0, 0)
    if len(sizes) >= 1:
        try:
            w1, h1 = int(sizes[0][0]), int(sizes[0][1])
        except Exception:
            w1, h1 = 0, 0
    if len(sizes) >= 2:
        try:
            w2, h2 = int(sizes[1][0]), int(sizes[1][1])
        except Exception:
            w2, h2 = 0, 0

    have1 = w1 > 0 and h1 > 0
    have2 = w2 > 0 and h2 > 0

    if not have1 and not have2:
        return ((0.0, 0.0, 1.0, 1.0), (0, 0, max(1, cw), max(1, ch)))

    # eager max when both present, per-image fallback otherwise
    if have1 and have2:
        pw = max(w1, w2)
        ph = max(h1, h2)
        geometry = resolve_canvas_content_geometry(
            widget_width=cw,
            widget_height=ch,
            image_width=pw,
            image_height=ph,
            virtual_layout=None,
        )
    elif have1:
        geometry = resolve_canvas_content_geometry(
            widget_width=cw,
            widget_height=ch,
            image_width=w1,
            image_height=h1,
            virtual_layout=None,
        )
    else:
        geometry = resolve_canvas_content_geometry(
            widget_width=cw,
            widget_height=ch,
            image_width=w2,
            image_height=h2,
            virtual_layout=None,
        )

    inner = geometry.inner_rect_px or (0, 0, cw, ch)
    # inner_rect_px is already int-truncated; keep round for parity with base_images
    ux, uy, uw, uh = inner
    try:
        ux_i = int(round(float(ux)))
        uy_i = int(round(float(uy)))
        uw_i = max(1, int(round(float(uw))))
        uh_i = max(1, int(round(float(uh))))
    except Exception:
        ux_i, uy_i, uw_i, uh_i = int(ux), int(uy), max(1, int(uw)), max(1, int(uh))

    letterbox = (
        ux_i / float(cw) if cw else 0.0,
        uy_i / float(ch) if ch else 0.0,
        uw_i / float(cw) if cw else 1.0,
        uh_i / float(ch) if ch else 1.0,
    )
    content_rect = (ux_i, uy_i, uw_i, uh_i)
    return (letterbox, content_rect)
