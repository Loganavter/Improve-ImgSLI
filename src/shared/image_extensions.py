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


def is_loadable_image_path(path) -> bool:
    """Return True if *path* is a loadable image file.

    Single home for the ``accepted-extension ∧ is_file`` admission rule
    (plan-cross-cutting-policy-2026-10-13, wave B1): every drop / dialog /
    loading entry point calls this instead of re-composing the two checks.
    The reducer stays the correctness gate; boundary call sites use this
    only to fail fast.

    Strictness (matches the strictest pre-B1 call site, the dialog-add
    validator, which composed accepted-extension with is_file):

    * directories → False (even when named ``*.png``);
    * missing paths → False;
    * broken symlinks → False;
    * symlinks resolving to a real file → True (``Path.is_file`` follows
      links);
    * ``str`` and ``Path`` inputs both accepted; undecodable inputs and
      filesystem errors → False.
    """
    from pathlib import Path as _Path

    try:
        p = path if isinstance(path, _Path) else _Path(str(path))
    except Exception:
        return False
    if not is_accepted_image_path(p):
        return False
    try:
        return bool(p.is_file())
    except Exception:
        return False


def has_image_urls(mime) -> bool:
    """Return True when *mime* carries at least one local image-file URL.

    Single home for the DnD accept verdict (wave B1): non-local URLs
    (``http://…``) are rejected even when the trailing path looks like an
    image — the loaders only read local files (``QUrl.toLocalFile()`` is
    ``""`` for remote URLs). Mirrors ``shared.image_drop``, which already
    gates on ``QUrl.isLocalFile()``. Tab-level copies (e.g. MC
    ``ui/drag_drop.has_image_urls``, B3-owned) should delegate here.
    """
    if mime is None or not mime.hasUrls():
        return False
    for url in mime.urls():
        try:
            if not url.isLocalFile():
                continue
        except Exception:
            continue
        if is_accepted_image_path(url.toLocalFile()):
            return True
    return False
