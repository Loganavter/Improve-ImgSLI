from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from PIL import ExifTags, Image

# The first-frame honesty row is a separate module (this one is at the
# file-size policy limit); re-exported here because callers reach the panel
# through this service, and the option rows they build are the same rows.
from .first_frame import first_frame_rows
from .values import (
    format_aspect_ratio,
    format_bytes,
    format_dpi,
    normalize_exif_value,
    stringify,
)


@dataclass(frozen=True)
class ImagePropertyRow:
    label_key: str
    fallback_label: str
    value: str
    value_key: str = ""
    fallback_value: str = ""
    #: Placeholders for a ``value_key`` translation that is not a constant,
    #: e.g. the frame_of key ("1 of {n}"). A tuple of pairs (not a dict) so the
    #: row stays frozen/hashable; :func:`apply_row_params` fills them in at
    #: render time, in whatever language the panel is drawn in.
    value_params: tuple[tuple[str, str], ...] = ()


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


def apply_row_params(text: str, params: tuple[tuple[str, str], ...]) -> str:
    """Fill ``{n}``-style placeholders of a translated row value.

    A translation that lost or renamed its placeholder must not raise inside
    rendering (a locale file is not code): the text is returned unfilled
    instead, which reads as a slightly clumsy row, not as a broken panel.
    """
    if not params:
        return text
    try:
        return text.format(**dict(params))
    except (KeyError, IndexError, ValueError):
        return text


def build_image_properties(
    *,
    path: str | Path | None,
    display_name: str = "",
    image: Any = None,
    app_rows: Iterable[tuple[str, str, Any]] = (),
    probe_image: bool = True,
) -> ImageProperties:
    source_path = Path(path) if path else None
    # Project packages (``.blinktable``, legacy ``.imgsli``) are not raster
    # images — probing them with Pillow only produces a misleading
    # "cannot identify image file" row.
    source_info = _read_source_info(source_path) if probe_image else {}
    dimensions = _image_dimensions(image) or source_info.get("dimensions")
    mode = _image_mode(image) or source_info.get("mode")
    channels = _image_channels(image, mode)
    if channels is None:
        channels = _channels_from_mode(mode)

    file_rows = _file_rows(source_path, display_name, source_info)
    image_rows = _image_rows(dimensions, mode, channels, source_info)
    # Appended last so the familiar Size / Color mode order never shifts.
    image_rows.extend(first_frame_rows(source_path, source_info))
    metadata_rows = _metadata_rows(source_info)
    app_section_rows = tuple(
        ImagePropertyRow(key, fallback, stringify(value))
        for key, fallback, value in app_rows
        if stringify(value)
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


_NON_IMAGE_SUFFIXES = frozenset({".blinktable", ".imgsli", ".imgsli-project"})


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
            if img.format != "PSD":
                # Frame count, for the first-frame notice. PSD is skipped on
                # purpose: its ``n_frames`` is the LAYER count, and reading it
                # parses the (large) layer section — the panel reports layers,
                # not frames. Absent key = no decoder reported a count, which
                # ``first_frame_notice`` handles by omitting the number.
                frames = getattr(img, "n_frames", None)
                if isinstance(frames, int) and frames > 0:
                    info["frame_count"] = frames
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
                    ExifTags.TAGS.get(tag, tag): normalize_exif_value(value)
                    for tag, value in exif.items()
                }
    except Exception as exc:
        _fill_from_shared_probes(path, info, exc)
    return info


def _fill_from_shared_probes(path: Path, info: dict[str, Any], exc: Exception) -> None:
    """Metadata for an accepted image Pillow cannot open.

    Pillow is the primary container parser, but it is not the only decoder the
    app ships with: a JXL (no Pillow plugin in most builds) still has its
    dimensions in the codestream header and is decoded by libvips/imagecodecs.
    Here the panel reports what those probes actually know — ``format``,
    ``dimensions``, and ``mode`` only from a real decode — and leaves exotic
    metadata (DPI/ICC/EXIF) ABSENT, which is the truth: they were not read.
    Absent keys render as no row; a bogus ``read_error`` row claimed the file
    itself was unreadable (2026-10-28, JXL properties panel).

    ``read_error`` is still reported when nothing could be measured, or when
    the suffix is not one the app claims to support at all.
    """
    try:
        from shared.image_extensions import is_accepted_image_path
    except Exception:
        info["read_error"] = str(exc)
        return
    if not is_accepted_image_path(path):
        info["read_error"] = str(exc)
        return
    try:
        from shared.image_processing.bounded_frame import detect_image_mode
        from shared.image_processing.progressive_loader import (
            get_image_dimensions,
            get_image_format_info,
        )
    except Exception:
        info["read_error"] = str(exc)
        return
    dimensions: tuple[int, int] | None = None
    try:
        dimensions = get_image_dimensions(str(path))
    except Exception as probe_exc:
        info["read_error"] = str(probe_exc)
        return
    if dimensions is None:
        # No header and no decoder: the file really is unreadable.
        info["read_error"] = str(exc)
        return
    info["dimensions"] = dimensions
    try:
        format_name, _progressive, _has_alpha = get_image_format_info(str(path))
        if format_name and format_name != "UNKNOWN":
            info["format"] = format_name
    except Exception:
        pass
    try:
        mode = detect_image_mode(str(path))
    except Exception:
        mode = None
    if mode:
        info["mode"] = mode

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
                        format_bytes(stat.st_size),
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
                format_aspect_ratio(width, height),
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
        rows.append(ImagePropertyRow("image_properties.dpi", "DPI", format_dpi(dpi)))
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
            rows.append(ImagePropertyRow(key, fallback, stringify(value)))
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


def _row_value(row: ImagePropertyRow, translate) -> str:
    if row.value_key:
        text = _translated(translate, row.value_key, row.fallback_value or row.value)
        return apply_row_params(text, row.value_params)
    return row.value or "-"


def _translated(translate, key: str, fallback: str) -> str:
    text = translate(key)
    return fallback if text == key else text
