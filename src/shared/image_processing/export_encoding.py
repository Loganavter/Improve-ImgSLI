"""Shared export encoding tail — single source for B4.

Unifies format/ext normalization, alpha-flattening, ``save_kwargs`` defaults,
and the ``SAVE_CANCELED_MESSAGE`` magic string across both tabs' export
services (``image_compare/services/image_export/service.py:212-343`` and
``multi_compare/services/image_export.py:34-85``).

Import via ``from shared.image_processing.export_encoding import ...``.
"""

from __future__ import annotations

from PIL import Image

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

_FORMATS_WITH_ALPHA = frozenset({"PNG", "TIFF", "WEBP", "JXL"})


def normalize_format(fmt: str | None) -> str:
    """Upper-case ``fmt`` with ``JPG`` → ``JPEG`` normalization."""
    raw = (fmt or "PNG").strip().upper()
    if raw == "JPG":
        return "JPEG"
    return raw


def resolve_extension(pil_format: str) -> str:
    """``.jpg`` for JPEG, ``.ext`` lower-cased otherwise."""
    lower = pil_format.lower().replace("jpeg", "jpg")
    return f".{lower}"


def flatten_alpha_if_needed(
    pil_image: Image.Image,
    image_format: str,
    background_color: tuple[int, int, int, int] | None,
) -> Image.Image:
    """Flatten RGBA → RGB when *image_format* lacks alpha support."""
    if pil_image.mode != "RGBA":
        return pil_image
    # BMP/JPEG never support alpha; others delegate to _FORMATS_WITH_ALPHA
    if image_format in _FORMATS_WITH_ALPHA:
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
    """Return PIL ``save_kwargs`` for *image_format*."""
    fmt = normalize_format(image_format)
    kwargs: dict = {}
    if fmt in {"JPEG", "WEBP"}:
        kwargs["quality"] = int(quality)
    elif fmt == "JPEG":  # unreachable due to above, kept for clarity
        kwargs["quality"] = int(quality)
    if fmt == "PNG":
        kwargs["compress_level"] = int(png_compress_level)
        kwargs["optimize"] = bool(png_optimize)
    # BMP/TIFF/JXL need no extra kwargs here; JXL handled via imagecodecs separately.
    # Ensure JPEG also covers WEBP duplicate above: WEBP already handled.
    # For JPEG we already set quality; for WEBP quality already set.
    # PNG needs both; others empty.
    # BMP explicit handling: alpha already flattened, no kwargs.
    return kwargs


def is_cancel_error(exc: BaseException) -> bool:
    """True when *exc* is the user-cancel sentinel."""
    return isinstance(exc, RuntimeError) and str(exc) == SAVE_CANCELED_MESSAGE
