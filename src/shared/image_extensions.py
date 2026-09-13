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


def build_image_dialog_filter(*, all_files_label: str = "All files (*)") -> str:
    """Build a ``QFileDialog`` filter from the single accepted-set source.

    Keeps every entries dialog (MC toolbar "Add images", IC dialogs) in
    sync with :data:`ACCEPTED_IMAGE_EXTENSIONS` so a newly accepted suffix
    (e.g. ``.jxl``) cannot be offered in one tab and bounced in another
    (bug-a1 drift). The trailing ``All files`` section is kept so users
    can still pick an edge-case file and get an explicit error-toast
    instead of a silent skip.
    """
    return f"Images ({IMAGE_FILTER_GLOB});;{all_files_label}"


def is_accepted_image_path(path) -> bool:
    """Return True if *path* has an accepted image suffix (case-insensitive)."""
    from pathlib import Path as _Path

    p = path if isinstance(path, _Path) else _Path(str(path))
    return p.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS
