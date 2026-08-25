"""Central accepted image extensions — single source of truth for drag&drop and dialogs.

Historically IC accepted ``.jxl`` while MC rejected it (cross-module review
2026-08-25 C9). All tabs/services must import from here so they stay in sync.
"""

from __future__ import annotations

# Lower-case dotted extensions, including JPEG XL.
ACCEPTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}
)

# Backwards-compatible alias — prefer ACCEPTED_IMAGE_EXTENSIONS in new code.
IMAGE_EXTENSIONS = ACCEPTED_IMAGE_EXTENSIONS

# Dialog filter fragment, e.g. ``"*.png *.jpg ..."`` for QFileDialog.
IMAGE_FILTER_GLOB = " ".join(f"*{ext}" for ext in sorted(ACCEPTED_IMAGE_EXTENSIONS))


def is_accepted_image_path(path) -> bool:
    """Return True if *path* has an accepted image suffix (case-insensitive)."""
    from pathlib import Path as _Path

    p = path if isinstance(path, _Path) else _Path(str(path))
    return p.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS
