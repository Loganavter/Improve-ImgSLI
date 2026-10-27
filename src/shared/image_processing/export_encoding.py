"""Shared export encoding tail — format/ext normalization and save kwargs.

Unifies format/ext normalization, alpha-flattening, ``save_kwargs`` defaults,
and the ``SAVE_CANCELED_MESSAGE`` magic string across both comparison tabs'
export services.

Which formats are writable at all, which suffixes name them, and the alpha set
live one level down in ``shared.image_processing.format_capability`` (that
module also owns the actual writer); re-exported here for the existing imports.

Import via ``from shared.image_processing.export_encoding import ...``.
"""

from __future__ import annotations

from PIL import Image

from shared.image_processing import pil_save as _pil_save_module
from shared.image_processing.format_capability import (
    formats_with_alpha,
    suffix_for_format,
)
from shared.image_processing.pil_save import SAVE_CANCELED_MESSAGE

# Re-export for single-import parity checks
__all__ = [
    "SAVE_CANCELED_MESSAGE",
    "normalize_format",
    "resolve_extension",
    "flatten_alpha_if_needed",
    "build_save_kwargs",
    "is_cancel_error",
]


def normalize_format(fmt: str | None) -> str:
    """Upper-case ``fmt`` with ``JPG`` → ``JPEG`` normalization."""
    raw = (fmt or "PNG").strip().upper()
    if raw == "JPG":
        return "JPEG"
    return raw


def resolve_extension(pil_format: str) -> str:
    """``.jpg`` for JPEG, the canonical suffix otherwise (shared definition)."""
    return suffix_for_format(pil_format)


def flatten_alpha_if_needed(
    pil_image: Image.Image,
    image_format: str,
    background_color: tuple[int, int, int, int] | None,
) -> Image.Image:
    """Flatten RGBA → RGB when *image_format* lacks alpha support."""
    if pil_image.mode != "RGBA":
        return pil_image
    # BMP/JPEG never support alpha; the rest is decided by the single
    # formats_with_alpha() definition in shared.image_processing.format_capability.
    if image_format in formats_with_alpha():
        return pil_image
    # Treat BMP as non-alpha as well (caller may pass "BMP")
    if image_format in {"JPEG", "BMP"}:
        bg = background_color or (255, 255, 255, 255)
        flat = Image.new("RGBA", pil_image.size, bg)
        # MC used alpha_composite, IC used paste(mask=alpha); both equivalent for opaque bg.
        try:
            flat.alpha_composite(pil_image)
        except Exception:
            flat.paste(pil_image, mask=pil_image.split()[3])
        return flat.convert("RGB")
    return pil_image


def build_save_kwargs(
    image_format: str,
    *,
    quality: int = 95,
    png_compress_level: int = 9,
    png_optimize: bool = True,
) -> dict:
    """Return PIL ``save_kwargs`` for *image_format*.

    ``quality`` is carried for JXL too: the shared writer translates it into
    libjxl's lossless/distance pair, so both tabs pass the same knob.
    """
    fmt = normalize_format(image_format)
    kwargs: dict = {}
    if fmt in {"JPEG", "WEBP", "JXL"}:
        kwargs["quality"] = int(quality)
    if fmt == "PNG":
        kwargs["compress_level"] = int(png_compress_level)
        kwargs["optimize"] = bool(png_optimize)
    # BMP/TIFF need no extra kwargs; alpha is already handled by the caller.
    return kwargs


def is_cancel_error(exc: BaseException) -> bool:
    """True when *exc* is the user-cancel sentinel."""
    sentinel = getattr(_pil_save_module, "SAVE_CANCELED_MESSAGE", SAVE_CANCELED_MESSAGE)
    return isinstance(exc, RuntimeError) and str(exc) == sentinel
