from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from PIL import ExifTags, Image


@dataclass(frozen=True)
class ImagePropertyRow:
    label_key: str
    fallback_label: str
    value: str
    value_key: str = ""
    fallback_value: str = ""


@dataclass(frozen=True)
class ImagePropertySection:
    title_key: str
    fallback_title: str
    rows: tuple[ImagePropertyRow, ...]


@dataclass(frozen=True)
class ImageProperties:
    title: str
    sections: tuple[ImagePropertySection, ...]

    def as_plain_text(self, translate) -> str:
        lines: list[str] = [self.title]
        for section in self.sections:
            rows = [row for row in section.rows if row.value or row.value_key]
            if not rows:
                continue
            lines.append("")
            lines.append(
                _translated(translate, section.title_key, section.fallback_title)
            )
            for row in rows:
                label = _translated(translate, row.label_key, row.fallback_label)
                value = _row_value(row, translate)
                lines.append(f"{label}: {value}")
        return "\n".join(lines)


def build_image_properties(
    *,
    path: str | Path | None,
    display_name: str = "",
    image: Any = None,
    app_rows: Iterable[tuple[str, str, Any]] = (),
    probe_image: bool = True,
) -> ImageProperties:
    source_path = Path(path) if path else None
    # Project packages (``.imgsli``) are not raster images — probing them with
    # Pillow only produces a misleading "cannot identify image file" row.
    source_info = _read_source_info(source_path) if probe_image else {}
    dimensions = _image_dimensions(image) or source_info.get("dimensions")
    mode = _image_mode(image) or source_info.get("mode")
    channels = _image_channels(image, mode)
    if channels is None:
        channels = _channels_from_mode(mode)

    file_rows = _file_rows(source_path, display_name, source_info)
    image_rows = _image_rows(dimensions, mode, channels, source_info)
    metadata_rows = _metadata_rows(source_info)
    app_section_rows = tuple(
        ImagePropertyRow(key, fallback, _stringify(value))
        for key, fallback, value in app_rows
        if _stringify(value)
    )

    sections = [
        ImagePropertySection(
            "image_properties.section_file",
            "File",
            tuple(file_rows),
        ),
        ImagePropertySection(
            "image_properties.section_image",
            "Image",
            tuple(image_rows),
        ),
    ]
    if app_section_rows:
        sections.append(
            ImagePropertySection(
                "image_properties.section_app",
                "In app",
                app_section_rows,
            )
        )
    if metadata_rows:
        sections.append(
            ImagePropertySection(
                "image_properties.section_metadata",
                "Metadata",
                tuple(metadata_rows),
            )
        )

    title = display_name or (source_path.name if source_path else "")
    return ImageProperties(title=title or "Image", sections=tuple(sections))


_NON_IMAGE_SUFFIXES = frozenset({".imgsli"})


def _read_source_info(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    if path.suffix.lower() in _NON_IMAGE_SUFFIXES:
        return {}
    info: dict[str, Any] = {}
    try:
        with Image.open(path) as img:
            info["format"] = img.format
            info["mode"] = img.mode
            info["dimensions"] = img.size
            dpi = img.info.get("dpi")
            if dpi:
                info["dpi"] = dpi
            if img.info.get("icc_profile"):
                info["color_profile"] = "ICC"
            try:
                exif = img.getexif()
            except Exception:
                exif = None
            if exif:
                info["exif"] = {
                    ExifTags.TAGS.get(tag, tag): _normalize_exif_value(value)
                    for tag, value in exif.items()
                }
    except Exception as exc:
        info["read_error"] = str(exc)
    return info

def _file_rows(
    path: Path | None,
    display_name: str,
    source_info: dict[str, Any],
) -> list[ImagePropertyRow]:
    rows = [
        ImagePropertyRow(
            "image_properties.name",
            "Name",
            display_name or (path.name if path else "-"),
        ),
        ImagePropertyRow("image_properties.path", "Path", str(path) if path else "-"),
    ]
    if path:
        suffix = path.suffix.lower().lstrip(".")
        rows.append(
            ImagePropertyRow(
                "image_properties.extension",
                "Extension",
                suffix.upper() if suffix else "-",
            )
        )
        if path.exists():
            try:
                stat = path.stat()
                rows.append(
                    ImagePropertyRow(
                        "image_properties.file_size",
                        "File size",
                        _format_bytes(stat.st_size),
                    )
                )
                rows.append(
                    ImagePropertyRow(
                        "image_properties.modified",
                        "Modified",
                        datetime.fromtimestamp(stat.st_mtime).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    )
                )
            except OSError:
                pass
    fmt = source_info.get("format")
    if fmt:
        rows.append(ImagePropertyRow("image_properties.format", "Format", str(fmt)))
    read_error = source_info.get("read_error")
    if read_error:
        rows.append(
            ImagePropertyRow(
                "image_properties.read_error", "Read error", str(read_error)
            )
        )
    return rows


def _image_rows(
    dimensions: tuple[int, int] | None,
    mode: str | None,
    channels: int | None,
    source_info: dict[str, Any],
) -> list[ImagePropertyRow]:
    rows: list[ImagePropertyRow] = []
    if dimensions:
        width, height = dimensions
        rows.append(
            ImagePropertyRow(
                "image_properties.size",
                "Size",
                f"{width} x {height} px",
            )
        )
        rows.append(
            ImagePropertyRow(
                "image_properties.megapixels",
                "Megapixels",
                f"{(width * height) / 1_000_000:.2f} MP",
            )
        )
        rows.append(
            ImagePropertyRow(
                "image_properties.aspect_ratio",
                "Aspect ratio",
                _format_aspect_ratio(width, height),
            )
        )
        if width > height:
            orientation_key, orientation_fallback = (
                "image_properties.orientation_landscape",
                "Landscape",
            )
        elif height > width:
            orientation_key, orientation_fallback = (
                "image_properties.orientation_portrait",
                "Portrait",
            )
        else:
            orientation_key, orientation_fallback = (
                "image_properties.orientation_square",
                "Square",
            )
        rows.append(
            ImagePropertyRow(
                "image_properties.orientation",
                "Orientation",
                "",
                orientation_key,
                orientation_fallback,
            )
        )
    if mode:
        rows.append(ImagePropertyRow("image_properties.color_mode", "Color mode", mode))
    if channels:
        rows.append(
            ImagePropertyRow("image_properties.channels", "Channels", str(channels))
        )
    dpi = source_info.get("dpi")
    if dpi:
        rows.append(ImagePropertyRow("image_properties.dpi", "DPI", _format_dpi(dpi)))
    color_profile = source_info.get("color_profile")
    if color_profile:
        rows.append(
            ImagePropertyRow(
                "image_properties.color_profile", "Color profile", color_profile
            )
        )
    return rows


def _metadata_rows(source_info: dict[str, Any]) -> list[ImagePropertyRow]:
    exif = source_info.get("exif") or {}
    wanted = (
        ("Make", "image_properties.camera_make", "Camera make"),
        ("Model", "image_properties.camera_model", "Camera model"),
        ("LensModel", "image_properties.lens", "Lens"),
        ("DateTimeOriginal", "image_properties.created", "Created"),
        ("DateTime", "image_properties.modified_metadata", "Metadata modified"),
        ("Software", "image_properties.software", "Software"),
        ("ExposureTime", "image_properties.exposure", "Exposure"),
        ("FNumber", "image_properties.aperture", "Aperture"),
        ("ISOSpeedRatings", "image_properties.iso", "ISO"),
        ("FocalLength", "image_properties.focal_length", "Focal length"),
    )
    rows: list[ImagePropertyRow] = []
    for exif_name, key, fallback in wanted:
        value = exif.get(exif_name)
        if value not in (None, ""):
            rows.append(ImagePropertyRow(key, fallback, _stringify(value)))
    return rows


def _image_dimensions(image: Any) -> tuple[int, int] | None:
    size = getattr(image, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        try:
            return int(size[0]), int(size[1])
        except (TypeError, ValueError):
            return None
    shape = getattr(image, "shape", None)
    if shape is not None and len(shape) >= 2:
        try:
            return int(shape[1]), int(shape[0])
        except (TypeError, ValueError):
            return None
    return None


def _image_mode(image: Any) -> str | None:
    mode = getattr(image, "mode", None)
    return str(mode) if mode else None


def _image_channels(image: Any, mode: str | None) -> int | None:
    shape = getattr(image, "shape", None)
    if shape is not None:
        if len(shape) == 2:
            return 1
        if len(shape) >= 3:
            try:
                return int(shape[2])
            except (TypeError, ValueError):
                return None
    return _channels_from_mode(mode)


def _channels_from_mode(mode: str | None) -> int | None:
    if not mode:
        return None
    return {
        "1": 1,
        "L": 1,
        "P": 1,
        "LA": 2,
        "RGB": 3,
        "YCbCr": 3,
        "LAB": 3,
        "HSV": 3,
        "RGBA": 4,
        "CMYK": 4,
    }.get(mode)


def _format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if abs(value) < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def _format_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "-"
    divisor = math.gcd(width, height)
    simplified = f"{width // divisor}:{height // divisor}"
    decimal = width / height
    return f"{simplified} ({decimal:.3f})"


def _format_dpi(dpi: Any) -> str:
    if isinstance(dpi, tuple) and len(dpi) >= 2:
        return f"{_stringify(dpi[0])} x {_stringify(dpi[1])}"
    return _stringify(dpi)


def _normalize_exif_value(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            return repr(value)
    if isinstance(value, tuple):
        return tuple(_normalize_exif_value(item) for item in value)
    return value


def _stringify(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple):
        return " x ".join(_stringify(item) for item in value)
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if isinstance(numerator, int) and isinstance(denominator, int) and denominator:
        if numerator > denominator:
            return f"{numerator / denominator:g}"
        return f"{numerator}/{denominator}"
    return str(value)


def _row_value(row: ImagePropertyRow, translate) -> str:
    if row.value_key:
        return _translated(translate, row.value_key, row.fallback_value or row.value)
    return row.value or "-"


def _translated(translate, key: str, fallback: str) -> str:
    text = translate(key)
    return fallback if text == key else text
