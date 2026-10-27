"""Shared export framebuffer tiling helpers.

UNITS. Two coordinate spaces meet here and this module is the only place
allowed to convert between them:

* **logical px** — what ``QWidget.resize()`` takes and what a logical-space
  canvas scene (image_compare export) lays itself out in;
* **framebuffer (device) px** — what ``grabFramebuffer()`` returns and what the
  RHI render target (``target.pixelSize()``) has.

They differ by the surface's ``devicePixelRatioF()``. ``export_framebuffer_scale``
/ ``export_surface_size`` are the single answer to "how many device px does the
export frame have": a caller that wants one framebuffer px per *output* px (so a
tile grab is pasted 1:1 into the output image) sizes the widget with
``export_surface_size`` and passes ``fit_framebuffer_to_target=True``. Callers
that keep a logical-space scene pass nothing (legacy shape: the widget is sized
in logical px, so a HiDPI grab is a device-px supersample that must be
downscaled at the end).

A grab whose size does not cover its target is never quietly resampled on a
DPR-fitted surface: ``resolve_export_framebuffer`` crops the sub-logical-pixel
rounding surplus, and raises ``ExportFramebufferMismatch`` otherwise (a
device-px grab against an output-px target used to shrink the composition to
the top-left ``1/DPR²`` of the frame).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterator
from typing import Any, Literal

import shiboken6 as sip
from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from core.log_names import APP_LOGGER_NAME
from engine.store.regions import build_uniform_tile_grid
from engine.gpu.offscreen_canvas import (
    configure_offscreen_widget,
    pump_offscreen_to_quiescence,
    render_widget_frame,
    resize_and_show_offscreen_widget,
)

DEFAULT_EXPORT_TILE_MAX_EXTENT = 4096

logger = logging.getLogger(APP_LOGGER_NAME)


class CanvasGoneError(RuntimeError):
    """Export canvas deleted mid-render — quiet abort, not a bug.

    Raised per tile/single so a tab closed mid-export fails the export
    silently instead of spraying ``already deleted`` tracebacks. The
    plugin layer maps this to a debug log (see gpu_export_proxy).
    """


class ExportFramebufferMismatch(RuntimeError):
    """A DPR-fitted grab does not cover the output tile/frame it must fill.

    Raised instead of resampling: a device-pixel grab shrunk to an output-pixel
    target would "succeed" while painting a composition into the top-left
    ``1/DPR²`` of the frame.
    """


def export_framebuffer_scale(widget: object) -> float:
    """Device (framebuffer) px per logical px of ``widget``'s render surface.

    THE single answer to "how many device px does the export frame have".
    Unknown widgets (fakes, non-Qt stubs) read as 1.0 — identity, no DPR.
    """
    try:
        scale = float(getattr(widget, "devicePixelRatioF")())  # type: ignore[attr-defined]
    except Exception:
        return 1.0
    return scale if scale > 0.0 else 1.0


def export_surface_size(
    widget: object, target_px: tuple[int, int]
) -> tuple[int, int]:
    """Logical widget size whose **framebuffer** covers ``target_px`` output px.

    Size adaptation only — rounding is upward, so the framebuffer is
    ``target_px`` … ``target_px + scale`` device px; the surplus is cropped
    (lossless) by :func:`resolve_export_framebuffer`, never resampled.
    """
    scale = export_framebuffer_scale(widget)
    return (
        max(1, math.ceil(int(target_px[0]) / scale)),
        max(1, math.ceil(int(target_px[1]) / scale)),
    )


def resolve_export_framebuffer(
    grab_size: tuple[int, int],
    target_px: tuple[int, int],
    *,
    scale: float,
    fit_framebuffer: bool,
    phase: str = "export",
) -> Literal["exact", "crop", "resample"]:
    """Classify one grab against the output target it must fill.

    ``"exact"`` — the grab already is the target grid (1:1, the normal case on
    a DPR-fitted surface); ``"crop"`` — the grab is larger by the sub-logical-px
    rounding of :func:`export_surface_size`, and because the composition origin
    is pinned to framebuffer ``(0, 0)`` the caller crops the top-left
    ``target_px`` (lossless); ``"resample"`` — legacy logical-space surface,
    where the framebuffer is a device-px *supersample* of the logical target by
    design, so the downscale is the intended final step (logged, never silent).

    A DPR-fitted grab that is smaller than its target, or larger by a whole
    logical px, is a units break: raises
    :class:`ExportFramebufferMismatch`.
    """
    grab_w, grab_h = int(grab_size[0]), int(grab_size[1])
    target_w, target_h = int(target_px[0]), int(target_px[1])
    if (grab_w, grab_h) == (target_w, target_h):
        return "exact"
    scale = max(1.0, float(scale))
    if fit_framebuffer:
        surplus_w = grab_w - target_w
        surplus_h = grab_h - target_h
        if 0 <= surplus_w < scale and 0 <= surplus_h < scale:
            return "crop"
        raise ExportFramebufferMismatch(
            f"{phase}: framebuffer {grab_w}x{grab_h} device px does not cover "
            f"the {target_w}x{target_h} output px target (scale {scale:g}) — "
            f"refusing to resample a device-pixel grab"
        )
    logger.warning(
        "export %s: framebuffer %dx%d device px vs %dx%d logical target "
        "(scale %.3g) — downscaling supersampled legacy logical-space surface",
        phase,
        grab_w,
        grab_h,
        target_w,
        target_h,
        scale,
    )
    return "resample"


def _ensure_live(widget) -> None:
    """Fail-open liveness probe; raises :class:`CanvasGoneError` when dead."""
    try:
        alive = widget is not None and bool(sip.isValid(widget))
    except Exception:
        alive = False
    if not alive:
        raise CanvasGoneError("export canvas widget deleted mid-render")


def iter_export_tile_rects(
    canvas_width: int, canvas_height: int, max_extent: int
) -> Iterator[tuple[int, int, int, int]]:
    """Yield ``(left, top, width, height)`` tile rects covering the export canvas."""
    grid = build_uniform_tile_grid(
        canvas_width, canvas_height, max_tile_width=max_extent
    )
    for row in range(grid.rows):
        top = row * grid.tile_height
        if top >= canvas_height:
            continue
        height = min(grid.tile_height, canvas_height - top)
        for col in range(grid.columns):
            left = col * grid.tile_width
            if left >= canvas_width:
                continue
            width = min(grid.tile_width, canvas_width - left)
            yield left, top, width, height


def qimage_to_pil_rgba(qimg: QImage) -> Image.Image:
    qimg_rgba = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes(
        "RGBA",
        (qimg_rgba.width(), qimg_rgba.height()),
        bytes(qimg_rgba.constBits()),
    )


class TiledFramebufferExporter:
    """Render a large canvas by tiling the offscreen widget framebuffer.

    ``fit_framebuffer_to_target=True`` sizes every surface so its framebuffer
    is the output tile in *device* px (one framebuffer px == one output px) —
    the scene must then be laid out in framebuffer px (``target.pixelSize()``),
    as multi_compare's projection is. The default (``False``) keeps the legacy
    logical-space behaviour (image_compare export): the widget is sized in
    logical px, so its HiDPI grab is a supersample that is downscaled once.
    """

    def __init__(
        self,
        widget: QWidget,
        *,
        set_export_viewport: Callable[[tuple[int, int, int, int] | None], None],
        prepare_frame: Callable[[], None],
        query_max_texture_size: Callable[[], int],
        fit_framebuffer_to_target: bool = False,
    ):
        self._widget = widget
        self._set_export_viewport = set_export_viewport
        self._prepare_frame = prepare_frame
        self._query_max_texture_size = query_max_texture_size
        self._fit_framebuffer = bool(fit_framebuffer_to_target)
        self._last_size: tuple[int, int] | None = None

    def render_rgba(
        self,
        canvas_w: int,
        canvas_h: int,
        *,
        max_extent: int = DEFAULT_EXPORT_TILE_MAX_EXTENT,
    ) -> Image.Image:
        tile_extent = min(max_extent, self._query_max_texture_size())
        if canvas_w <= tile_extent and canvas_h <= tile_extent:
            return self._render_single(canvas_w, canvas_h)

        final_image = Image.new("RGBA", (canvas_w, canvas_h))
        for tile_left, tile_top, tile_w, tile_h in iter_export_tile_rects(
            canvas_w, canvas_h, tile_extent
        ):
            tile_image = self._render_tile(canvas_w, canvas_h, tile_left, tile_top, tile_w, tile_h)
            final_image.paste(tile_image, (tile_left, tile_top))
        self._set_export_viewport(None)
        return final_image

    def _prepare_surface(self, target: tuple[int, int]) -> None:
        """Resize the offscreen widget so its framebuffer covers ``target``."""
        if self._fit_framebuffer:
            logical = export_surface_size(self._widget, target)
        else:
            logical = target
        if self._last_size != logical:
            resize_and_show_offscreen_widget(self._widget, logical)
            self._last_size = logical

    def _read_frame(self, target: tuple[int, int], *, phase: str) -> Image.Image:
        """Grab the framebuffer and map it onto ``target`` output px (no guess)."""
        try:
            qimg = self._widget.grabFramebuffer()  # type: ignore[attr-defined]  # duck-typed GL surface
        except RuntimeError as exc:
            raise CanvasGoneError(f"export canvas deleted during {phase} grab: {exc}") from exc
        image = qimage_to_pil_rgba(qimg)
        mode = resolve_export_framebuffer(
            image.size,
            target,
            scale=export_framebuffer_scale(self._widget),
            fit_framebuffer=self._fit_framebuffer,
            phase=phase,
        )
        if mode == "crop":
            return image.crop((0, 0, int(target[0]), int(target[1])))
        if mode == "resample":
            return image.resize(target, Image.Resampling.BILINEAR)
        return image

    def _render_single(self, canvas_w: int, canvas_h: int) -> Image.Image:
        _ensure_live(self._widget)
        self._set_export_viewport(None)
        target = (canvas_w, canvas_h)
        self._prepare_surface(target)
        self._prepare_frame()
        render_widget_frame(self._widget)
        # Cold-tier first frame: residency uploads are budget-limited per
        # frame, so a single grab can read back a partial tier. Pump to
        # quiescence (no-op when already resident) before the grab.
        pump_offscreen_to_quiescence(self._widget)
        return self._read_frame(target, phase="single frame")

    def _render_tile(
        self,
        canvas_w: int,
        canvas_h: int,
        tile_left: int,
        tile_top: int,
        tile_w: int,
        tile_h: int,
    ) -> Image.Image:
        target = (tile_w, tile_h)
        _ensure_live(self._widget)
        self._prepare_surface(target)
        # Viewport in FRAMEBUFFER px of the full export frame: with the surface
        # fitted to the target that is the same grid as output px (see module
        # header), which is what the scene projects into.
        self._set_export_viewport((canvas_w, canvas_h, tile_left, tile_top))
        self._prepare_frame()
        render_widget_frame(self._widget)
        # Same cold-tier rationale as _render_single: the first tile of a
        # fresh tier is the likeliest partial grab; pump before reading.
        pump_offscreen_to_quiescence(self._widget)
        return self._read_frame(target, phase=f"tile {tile_left},{tile_top}")


