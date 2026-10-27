"""Bounded PIL frames for the measurement tier (no Qt).

The preview tier (:mod:`shared.image_processing.progressive_loader`) hands the
canvas a ``QImage``; the gallery triage measures with PIL (dHash, HSV
embedding, Laplacian sharpness, EXIF probe). Both must describe the SAME
pixels, so this module reuses the preview tier's decoder — libvips
``thumbnail`` when the installed build can stream the format, then the JXL
imagecodecs path, then PIL — and only swaps the adapter.

It exists as its own module because a format Pillow has no plugin for (JXL in
most builds) would otherwise fall through every measurement as "unreadable"
and score a silent zero. ``None`` from :func:`load_bounded_frame` is the
honest "no backend could decode this" answer — callers must never turn it into
a zero measurement.

Dependency direction (kept acyclic): ``progressive_loader`` imports this
module; this module reads ``progressive_loader``'s capability flags, bound and
error type through a LAZY import inside each function, so ``JXL_SUPPORTED``
and ``ImageSizeLimitError`` are the same objects the loader sees (no second
flag that can drift, no import cycle).
"""

from __future__ import annotations

from typing import Any

from PIL import Image

#: PIL mode for a decoded frame's band count. The ONLY mapping of its kind —
#: a probe may report "RGBA" because pixels arrived with four bands, never
#: because a caller guessed it.
PIL_MODE_BY_BANDS = {1: "L", 2: "LA", 3: "RGB", 4: "RGBA"}


def frame_from_array(arr: Any) -> "Image.Image":
    """PIL frame whose mode follows the actual band count (no invented alpha)."""
    bands = int(arr.shape[2]) if getattr(arr, "ndim", 0) == 3 else 1
    mode = PIL_MODE_BY_BANDS.get(bands)
    if mode is None:
        raise ValueError(f"unsupported band count for a decoded frame: {bands}")
    return Image.fromarray(arr, mode)


def vips_thumbnail_array(image_path: str, max_edge: int) -> Any:
    """``pyvips.Image.thumbnail`` → uint8 ``(h, w, bands)`` array. Raises on failure.

    ONE streaming decode for every consumer that wants a bounded frame:
    ``progressive_loader.load_preview_image`` adapts it to ``QImage`` (display
    tier) and :func:`load_bounded_frame` to PIL (measurement tier).
    """
    import numpy as np
    import pyvips

    thumb = pyvips.Image.thumbnail(
        image_path, max_edge, height=max_edge, size=pyvips.enums.Size.DOWN
    )
    if not thumb.hasalpha():
        thumb = thumb.bandjoin(255)
    if thumb.format != "uchar":
        thumb = thumb.cast("uchar")
    return np.ndarray(
        buffer=thumb.write_to_memory(),
        dtype=np.uint8,
        shape=(thumb.height, thumb.width, thumb.bands),
    )


def load_bounded_frame(image_path: str, max_edge: int = 1024) -> "Image.Image | None":
    """Bounded PIL frame (long edge ≤ ``max_edge``) for the measurement tier.

    ``None`` = no backend could decode this file. That is the "not measured"
    signal: a caller must never turn it into a zero measurement.
    """
    from shared.image_processing import progressive_loader as loader

    try:
        cap = max(1, int(max_edge))
    except (TypeError, ValueError):
        return None
    if loader.pyvips_can_stream(image_path):
        try:
            return frame_from_array(vips_thumbnail_array(image_path, cap))
        except loader.ImageSizeLimitError:
            raise
        except Exception as e:
            loader.logger.debug(f"vips bounded frame failed for {image_path}: {e}")
    if loader.JXL_SUPPORTED and str(image_path).lower().endswith(".jxl"):
        try:
            # Header-first bound: ``imread`` allocates the full frame, so an
            # oversized JXL must be refused before it (same rule as
            # ``load_preview_image``).
            header_dims = loader.read_jxl_header_dimensions(image_path)
            if header_dims is not None:
                loader._ensure_supported_dimensions(header_dims[0], header_dims[1], image_path)
            frame = frame_from_array(loader.imagecodecs.imread(image_path))
            frame.thumbnail((cap, cap), Image.Resampling.BILINEAR)
            return frame
        except loader.ImageSizeLimitError:
            raise
        except Exception as e:
            loader.logger.error(f"Failed to decode bounded JXL frame {image_path}: {e}")
            return None
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            loader._ensure_supported_dimensions(
                width, height, image_path, ignore_limit=loader.pyvips_can_stream(image_path)
            )
            frame = img.copy()
            frame.thumbnail((cap, cap), Image.Resampling.BILINEAR)
            return frame
    except loader.ImageSizeLimitError:
        raise
    except Exception as e:
        loader.logger.debug(f"PIL bounded frame failed for {image_path}: {e}")
        return None


def detect_image_mode(image_path: str) -> str | None:
    """Colour mode name from the cheapest honest probe, or None.

    Header-only when libvips can stream the file (``new_from_file`` exposes
    ``bands`` without decoding pixels), else the bounded frame. None means
    "unknown" and consumers must show the row as absent — never assume RGBA.
    """
    from shared.image_processing import progressive_loader as loader

    if loader.pyvips_can_stream(image_path):
        try:
            import pyvips

            bands = int(pyvips.Image.new_from_file(str(image_path), access="sequential").bands)
            mode = PIL_MODE_BY_BANDS.get(bands)
            if mode is not None:
                return mode
        except Exception as e:
            loader.logger.debug(f"vips header band probe failed for {image_path}: {e}")
    frame = load_bounded_frame(str(image_path))
    return frame.mode if frame is not None else None


__all__ = ["PIL_MODE_BY_BANDS", "detect_image_mode", "frame_from_array", "load_bounded_frame", "vips_thumbnail_array"]
