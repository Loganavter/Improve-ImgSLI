"""Recording adapter for the GPU filmstrip band (strip atlas, phase 2).

``strip_window.build_window`` is duck-typed: it asks the recording for
``evaluate_at(timestamp)``, ``images_for(snapshot, tile_size)`` and a
``layout``. The editor recording knows the first two; the BLOCK geometry
belongs to the timeline (``strip_block_layout`` — block x, block width and the
block's representative frame — plus ``get_base_tile_width`` for the base
tile). This module is the one place that joins them, so the renderer never
carries a second geometry formula:

* :func:`timeline_strip_layout` converts the timeline's visible blocks into a
  :class:`StripBlockLayout` the renderer accepts. ``block_time`` maps a block
  to its representative FRAME (the toolkit's own ``rep_frame``) over the
  timeline fps — a block is not a frame: at the fitted zoom one block spans
  several frames, and ``block / fps`` would ask the recording for the wrong
  instant (owner-visible: every tile showing frame 0's neighbourhood).
* :class:`StripRecordingAdapter` is the object handed to ``build_window``:
  ``evaluate_at`` delegates to the recording, ``images_for`` delegates to the
  exporter's proxy seam (never a decode on the interaction path).
* :func:`proxy_pair_for` builds that proxy seam out of
  ``VideoExporterService._resolve_thumbnail_images`` — the same call the
  thumbnail/export paths use, so a strip tile and its thumbnail share one
  source resolution (pyramid coarse level / display cache, or a miss).

Nothing here is GPU-aware and nothing here waits: one pure-CPU call per view
change, no timer, no settle gate, no worker.
"""

from __future__ import annotations

from dataclasses import dataclass

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)

from tabs.image_compare.services.video_snapshot_rendering.strip_window import (
    LAYER_PX,
    StripBlockLayout,
)

#: Blocks in one window. The window is one texture array with two layers per
#: tile, and a band shows ~viewport/base-tile blocks (11 for a 1200 px strip,
#: 60 for a 4K one); the cap keeps one window's array and upload batch bounded
#: without ever dropping the blocks the user is looking at on a normal screen.
MAX_BLOCKS = 64


@dataclass(frozen=True)
class TimelineStripLayout(StripBlockLayout):
    """The timeline's strip blocks as the renderer's block layout.

    ``block_frames`` are the block representatives the toolkit's own
    ``strip_block_layout`` returned for the visible window (``first_block`` is
    the absolute block index of ``block_frames[0]``). ``block_time`` therefore
    reproduces the exact frame the QPainter strip would have drawn, while the
    tile size / fps / column count stay plain layout data.
    """

    first_block: int = 0
    block_frames: tuple[int, ...] = ()

    def block_time(self, block: int) -> float:
        index = int(block) - int(self.first_block)
        if 0 <= index < len(self.block_frames):
            return int(self.block_frames[index]) / float(self.fps)
        return super().block_time(block)


def strip_visible_span(timeline):
    """``(content_start_x, start_x, end_x)`` of the visible strip, or ``None``.

    Expressed with the toolkit's public geometry helpers only — the block
    geometry itself is never re-derived here (``strip_block_layout`` owns it);
    this is just the interval that layout is asked about, the same one the
    toolkit's own ``visible_strip_block_range`` uses. Degenerate view = no
    window (fail-open: the band keeps its previous frame).
    """
    try:
        scroll_area = timeline_viewport.get_scroll_area(timeline)
        scroll_x = (
            scroll_area.horizontalScrollBar().value()
            if scroll_area is not None
            else 0
        )
        content_start_x = float(timeline.LEFT_GUTTER)
        logical_width = float(timeline_viewport.get_logical_width(timeline))
        viewport_width = float(timeline_viewport.get_viewport_width(timeline))
        inset = float(timeline_viewport.right_inset(timeline))
    except Exception:
        return None
    if logical_width <= 0 or viewport_width <= 0:
        return None
    start_x = max(content_start_x, float(scroll_x))
    end_x = min(
        float(scroll_x) + viewport_width - inset,
        content_start_x + logical_width,
    )
    if end_x <= start_x:
        return None
    return (content_start_x, start_x, end_x)


def timeline_strip_layout(timeline, *, fps):
    """``(layout, first_block, count)`` for the band's current view, or ``None``.

    One ``strip_block_layout`` call decides every number here: the first
    visible block, the block count, each block's representative frame and the
    block width (which becomes the tile width). ``STRIP_HEIGHT`` is the block
    height. Columns equal blocks because the band is one row — so tile ``i``
    of the window lands on block ``i`` of the strip.
    """
    try:
        total = int(getattr(timeline, "_total_frames", 0) or 0)
    except Exception:
        return None
    if total <= 0 or not fps or float(fps) <= 0:
        return None
    span = strip_visible_span(timeline)
    if span is None:
        return None
    content_start_x, start_x, end_x = span
    try:
        blocks = timeline_viewport.strip_block_layout(
            timeline,
            content_start_x=content_start_x,
            start_x=start_x,
            end_x=end_x,
            overscan_blocks=0,
        )
    except Exception:
        return None
    if not blocks:
        return None
    draw_w = float(blocks[0][1])
    if draw_w <= 0.0:
        return None
    try:
        strip_height = float(timeline.STRIP_HEIGHT)
    except Exception:
        return None
    if strip_height <= 0.0:
        return None
    first_block = max(0, int(round((blocks[0][0] - content_start_x) / draw_w)))
    visible = blocks[:MAX_BLOCKS]
    # One tile is uploaded 1:1 into one array layer (``strip_window.LAYER_PX``),
    # so a block wider than a layer is planned at the layer size; the pass
    # stretches the window grid over the band, which keeps each tile on its own
    # block cell. The cap only bites at extreme zoom, never at the fitted view.
    tile_w = min(int(round(draw_w)), int(LAYER_PX))
    tile_h = min(int(round(strip_height)), int(LAYER_PX))
    if tile_w <= 0 or tile_h <= 0:
        return None
    layout = TimelineStripLayout(
        tile_size=(tile_w, tile_h),
        fps=float(fps),
        block_count=len(visible),
        cols=len(visible),
        first_block=first_block,
        block_frames=tuple(int(block[2]) for block in visible),
    )
    return layout, first_block, len(visible)


class StripRecordingAdapter:
    """The ``recording`` object ``build_window`` expects, over the editor.

    ``layout`` is set per view change (see :func:`timeline_strip_layout`);
    ``fps`` and ``block_count`` mirror it so the renderer's fallback path and
    its diagnostics read the same numbers the timeline drew.
    """

    def __init__(self, recording, *, proxy_pair, layout=None, fps=None):
        self._recording = recording
        self._proxy_pair = proxy_pair
        self.layout = layout
        fallback_fps = getattr(recording, "fps", 10.0)
        self.fps = float(fps or fallback_fps or 10.0)
        self.block_count = int(getattr(layout, "block_count", 0) or 0)

    def evaluate_at(self, timestamp):
        """The frame state at ``timestamp`` — the recording's own evaluation."""
        return self._recording.evaluate_at(float(timestamp))

    def images_for(self, snapshot, tile_size):
        """The session's proxy pair for ``snapshot`` at ``tile_size``.

        ``None`` means "no proxy at this size" — the renderer draws a
        fail-closed placeholder tile of its own layer. Never a decode: the
        seam is the exporter's pyramid/display-cache lookup.
        """
        pair = self._proxy_pair(snapshot, (int(tile_size[0]), int(tile_size[1])))
        if not pair:
            return None
        image1, image2 = pair[0], pair[1]
        if image1 is None or image2 is None:
            return None
        return (image1, image2)


def proxy_pair_for(exporter, *, auto_crop=False):
    """``pair_for(snapshot, tile_size)`` over the exporter's proxy seam.

    Uses ``VideoExporterService._resolve_thumbnail_images`` — the resolver the
    thumbnail and export paths already go through, including the injected
    session-state/pyramid resolver. Returns ``None`` when the exporter has no
    such seam (test doubles, a stale exporter), which the adapter turns into a
    placeholder tile rather than a decode.
    """
    resolve = getattr(exporter, "_resolve_thumbnail_images", None)
    if not callable(resolve):
        return None

    def _pair(snapshot, tile_size):
        (image1, image2), _kinds = resolve(
            snapshot,
            bool(auto_crop),
            (max(1, int(tile_size[0])), max(1, int(tile_size[1]))),
        )
        return (image1, image2)

    return _pair


__all__ = [
    "MAX_BLOCKS",
    "StripRecordingAdapter",
    "TimelineStripLayout",
    "proxy_pair_for",
    "strip_visible_span",
    "timeline_strip_layout",
]
