"""Saving helpers owned by the Multi Compare tab."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage


def qimage_to_pil(image: QImage) -> Image.Image:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()
    ptr = converted.bits()
    return Image.frombytes("RGBA", (width, height), bytes(ptr))


def save_composite(image: QImage, options: dict) -> str:
    output_dir = Path(options["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    image_format = str(options.get("format", "PNG")).upper()
    extension = ".jpg" if image_format == "JPEG" else f".{image_format.lower()}"
    output_path = _next_available_path(
        output_dir / f"{options['file_name']}{extension}"
    )

    pil_image = qimage_to_pil(image)
    save_kwargs: dict = {}
    if image_format in {"JPEG", "BMP"}:
        background = tuple(options.get("background_color") or (255, 255, 255, 255))
        flattened = Image.new("RGBA", pil_image.size, background)
        flattened.alpha_composite(pil_image)
        pil_image = flattened.convert("RGB")
    if image_format in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = int(options.get("quality", 95))
    if image_format == "PNG":
        save_kwargs["compress_level"] = int(options.get("png_compress_level", 9))
        save_kwargs["optimize"] = bool(options.get("png_optimize", True))

    pil_image.save(output_path, format=image_format, **save_kwargs)
    return str(output_path)


def _next_available_path(path: Path) -> Path:
    """Return ``path`` or a suffixed variant that does not exist yet."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
