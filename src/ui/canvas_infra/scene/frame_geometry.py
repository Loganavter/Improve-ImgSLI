from __future__ import annotations

from dataclasses import dataclass

from shared.rendering import VirtualCanvasLayout
from ui.canvas_infra.scene.layout_requirements import resolve_feature_virtual_layout
from ui.canvas_infra.viewport.geometry import QuickContentRect


@dataclass(frozen=True)
class ContentGeometry:
    """Widget-px geometry for one frame, derived fresh from current inputs —
    no cached field to invalidate. ``canvas_*`` is the virtual canvas size at
    native image resolution (image + feature padding); ``outer_rect`` is
    where that whole virtual canvas sits inside the widget; ``inner_rect`` is
    where the actual image sits inside ``outer_rect`` (equal to it when no
    feature currently requires padding). This is the single owner of this
    computation: live rendering, still-image export, and video export must
    all call ``resolve_canvas_content_geometry`` (or its store-driven
    wrapper) instead of recomputing letterbox/padding math locally — see
    docs/dev/QRHI_CANVAS_FEATURES.md."""

    canvas_width: int
    canvas_height: int
    outer_rect: QuickContentRect | None
    inner_rect: QuickContentRect | None

    @property
    def outer_rect_px(self) -> tuple[int, int, int, int] | None:
        if self.outer_rect is None:
            return None
        r = self.outer_rect
        return (int(r.x), int(r.y), int(r.width), int(r.height))

    @property
    def inner_rect_px(self) -> tuple[int, int, int, int] | None:
        if self.inner_rect is None:
            return None
        r = self.inner_rect
        return (int(r.x), int(r.y), int(r.width), int(r.height))


def resolve_canvas_content_geometry(
    *,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
    virtual_layout: VirtualCanvasLayout | None,
) -> ContentGeometry:
    """Compute this frame's letterbox + feature-padding geometry from
    scratch. Pull, not push: callers are expected to call this every frame
    (e.g. from a render pass's ``prepare()`` or a resize handler) rather than
    cache the result across frames, so a feature's ``render.layout_requirement``
    changing (e.g. the magnifier needing more space) is reflected on the very
    next frame without any explicit invalidation wiring.

    ``virtual_layout=None`` (or a layout with unit ``canvas_bounds``) is the
    plain no-padding case: ``outer_rect == inner_rect``, identical to the
    old ``build_content_rect`` letterbox fit."""
    if widget_width <= 0 or widget_height <= 0 or image_width <= 0 or image_height <= 0:
        return ContentGeometry(
            canvas_width=max(1, widget_width),
            canvas_height=max(1, widget_height),
            outer_rect=None,
            inner_rect=None,
        )

    if virtual_layout is not None:
        pad_left, pad_right, pad_top, pad_bottom = virtual_layout.resolve_padding_pixels(
            base_width=image_width,
            base_height=image_height,
        )
    else:
        pad_left = pad_right = pad_top = pad_bottom = 0

    canvas_w = image_width + pad_left + pad_right
    canvas_h = image_height + pad_top + pad_bottom

    ratio = min(widget_width / canvas_w, widget_height / canvas_h)
    outer_w = max(1.0, canvas_w * ratio)
    outer_h = max(1.0, canvas_h * ratio)
    outer_x = (widget_width - outer_w) / 2.0
    outer_y = (widget_height - outer_h) / 2.0

    inner_w = max(1.0, image_width * ratio)
    inner_h = max(1.0, image_height * ratio)
    inner_x = outer_x + pad_left * ratio
    inner_y = outer_y + pad_top * ratio

    return ContentGeometry(
        canvas_width=canvas_w,
        canvas_height=canvas_h,
        outer_rect=QuickContentRect(x=outer_x, y=outer_y, width=outer_w, height=outer_h),
        inner_rect=QuickContentRect(x=inner_x, y=inner_y, width=inner_w, height=inner_h),
    )


def resolve_canvas_content_geometry_for_store(
    store,
    *,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
) -> ContentGeometry:
    """Convenience wrapper for callers that only have a ``store`` — resolves
    the ``VirtualCanvasLayout`` via ``resolve_feature_virtual_layout`` (the
    single owner of the feature-requirement union) and forwards to
    ``resolve_canvas_content_geometry``."""
    virtual_layout = resolve_feature_virtual_layout(
        store,
        drawing_width=image_width,
        drawing_height=image_height,
    )
    return resolve_canvas_content_geometry(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=image_width,
        image_height=image_height,
        virtual_layout=virtual_layout,
    )


def resolve_image_space_visible_rect(
    geometry: ContentGeometry,
    *,
    widget_rect_px: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float] | None:
    """Invert a widget-space rect (e.g. the visible viewport, or the
    magnifier capture rect) back to source-image pixel space, the coordinate
    system ``TileGrid``/``TileTextureService.visible_tiles`` operate in
    (docs/dev/TILED_RENDERING_DESIGN.md, "Coordinate mapping"). This is the
    one place that walks the widget->canvas->image chain backward; it stays
    next to ``resolve_canvas_content_geometry`` (the forward direction) so
    geometry math has a single owner in both directions. Not yet called from
    the live render loop — Phase 0's base quad draw always requests every
    tile in the grid; viewport-driven ``visible_tiles`` calls land in Phase 2.
    """
    inner = geometry.inner_rect
    if inner is None or inner.width <= 0 or inner.height <= 0:
        return None
    scale_x = image_width / inner.width
    scale_y = image_height / inner.height
    left, top, right, bottom = widget_rect_px
    image_left = (left - inner.x) * scale_x
    image_top = (top - inner.y) * scale_y
    image_right = (right - inner.x) * scale_x
    image_bottom = (bottom - inner.y) * scale_y
    return (
        max(0.0, min(image_left, float(image_width))),
        max(0.0, min(image_top, float(image_height))),
        max(0.0, min(image_right, float(image_width))),
        max(0.0, min(image_bottom, float(image_height))),
    )


def resolve_canvas_clip_rect_px(
    virtual_layout: VirtualCanvasLayout | None,
    *,
    base_width: int,
    base_height: int,
    content_offset_px: tuple[int, int] = (0, 0),
    content_size_px: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Where the real image content sits inside the padded virtual canvas, in
    canvas-pixel units where (0, 0) is the canvas's top-left corner and pixel
    scale is ``base_width``x``base_height`` (the un-padded content box the
    image was fitted into).

    ``content_offset_px``/``content_size_px`` additionally account for
    centering when the source had to be scaled down to fit inside that box
    ((0, 0) / None when no such extra fit-down happened, the common case).

    Feature-agnostic: this function knows nothing about split positions,
    overlays, or any specific feature — it only maps a ``VirtualCanvasLayout``
    to a pixel rect. Single owner of this computation across live/export/
    video paths — see docs/dev/QRHI_CANVAS_FEATURES.md."""
    if virtual_layout is not None:
        pad_left_px, _, pad_top_px, _ = virtual_layout.resolve_padding_pixels(
            base_width=base_width, base_height=base_height
        )
    else:
        pad_left_px = pad_top_px = 0
    offset_x, offset_y = content_offset_px
    clip_x = pad_left_px + int(offset_x)
    clip_y = pad_top_px + int(offset_y)
    if content_size_px is not None:
        clip_w, clip_h = content_size_px
    else:
        clip_w, clip_h = base_width, base_height
    return (clip_x, clip_y, max(1, int(clip_w)), max(1, int(clip_h)))
