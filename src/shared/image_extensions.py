"""Central image-format canon — single source of truth for drag&drop and dialogs.

Three groups live here because three different consumers read them, and a
suffix admitted by one entry point but bounced by another is the drift this
module exists to stop (historically IC accepted ``.jxl`` while MC rejected it —
cross-module review 2026-08-25 C9; then ``.avif`` decoded fine for months while
the static set still bounced it from DnD, dialogs and the gallery scan).

* :data:`ACCEPTED_IMAGE_EXTENSIONS` — group A (single-frame rasters) plus
  group B (first frame / flattened composite). Every DnD gate, file dialog,
  folder scan and load path decides with this set.
* :data:`FIRST_FRAME_SUFFIXES` — the group B subset. Those files ARE accepted,
  but only one frame of them is ever shown, so a surface that presents one must
  say "first frame" instead of pretending the whole document is on screen.
* :data:`REJECTED_SUFFIXES` — group C: formats users will actually try, each
  with the reason we refuse it, so a refusal reads as "PDF document, not a
  frame" rather than "could not load the image".

The accepted set is an **assertion about the installed decoders**, not a wish
list, so ``tests/contracts/test_accepted_formats_match_decoders.py`` re-probes
it on every run: Pillow's opener list, the shrink-only non-Pillow allowlist
(``.jxl``), and a runtime round trip per suffix (write a tiny sample → admit →
dimensions → preview) wherever this stack has a writer for the format. Never
add a suffix here without making that gate pass — "accept it and let the load
fail" is exactly the hole the gate closes.

Group C is a *product policy*, not a capability claim: a few of those formats
do decode on some machines (``.h5`` with h5py, ``.eps`` through a system
Ghostscript, ``.heic`` through a libvips built with libheif) and are still
refused, because a page, a scientific dataset or a camera RAW is not a frame
the comparison tabs can align.
"""

from __future__ import annotations

#: Group A — one raster, one frame, decoded straight into the tiled store.
#: Sorted; the first nine entries are the historical canon (``.jxl`` and
#: ``.avif`` were added after their decoder probes), the rest is the 2026-10-28
#: format-expansion wave (imgslI audit: decoders already read them, the lists
#: did not).
_GROUP_A_SUFFIXES: frozenset[str] = frozenset(
    {
        # Historical canon.
        ".avif",
        ".bmp",
        ".jpeg",
        ".jpg",
        ".jxl",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
        # Still rasters with a real decode path on this stack.
        ".blp",
        ".bw",
        ".cur",
        ".dds",
        ".dib",
        ".ftc",
        ".ftu",
        ".gbr",
        ".icns",
        ".ico",
        ".im",
        ".j2c",
        ".j2k",
        ".jp2",
        ".jpc",
        ".jpf",
        ".jpx",
        ".msp",
        ".pbm",
        ".pcx",
        ".pgm",
        ".pnm",
        ".ppm",
        ".pxr",
        ".qoi",
        ".ras",
        ".rgb",
        ".rgba",
        ".sgi",
        ".tga",
        ".xbm",
        ".xpm",
    }
)

#: Group B — accepted, but only one frame (or one flattened composite) of the
#: file is shown: ``.gif``/``.fli``/``.flc`` animation, ``.apng``/``.avifs``
#: sequences, ``.mpo`` multi-picture, ``.dcx`` multi-page PCX, ``.psd`` layers.
#: The viewer has no animation or layer support, so a UI that presents one of
#: these must SAY "first frame" / "layers flattened" — the wording is a separate
#: i18n pass, the honesty obligation is this set.
#:
#: Multi-page ``.tiff`` and animated ``.webp`` already behaved this way before
#: this group existed and stay in group A: their suffix is not a
#: sequence-container suffix (a plain ``.tiff``/``.webp`` is a single image, so
#: a blanket "first frame" label on the suffix would be wrong for the common
#: case). They are the precedent that makes admitting group B consistent at
#: all — one frame is what the viewer shows for those too.
FIRST_FRAME_SUFFIXES: frozenset[str] = frozenset(
    {
        ".apng",
        ".avifs",
        ".dcx",
        ".flc",
        ".fli",
        ".gif",
        ".mpo",
        ".psd",
    }
)

#: Group A + B: every suffix any entry point may admit.
ACCEPTED_IMAGE_EXTENSIONS: frozenset[str] = (
    _GROUP_A_SUFFIXES | FIRST_FRAME_SUFFIXES
)

# Backwards-compatible alias — prefer ACCEPTED_IMAGE_EXTENSIONS in new code.
IMAGE_EXTENSIONS = ACCEPTED_IMAGE_EXTENSIONS

#: One reason shared by every camera-RAW suffix: the file is sensor data plus an
#: embedded preview, so "just decode it" is not a decoder question.
_RAW_REASON = (
    "Camera RAW: needs demosaicing (rawpy/libraw), which is not a dependency; "
    "the embedded JPEG preview is not the image."
)

#: Group C — deliberately NOT accepted, with the reason a user-facing refusal
#: should repeat. Keys never overlap :data:`ACCEPTED_IMAGE_EXTENSIONS`
#: (``tests/contracts/test_rejected_formats_have_reasons.py`` enforces it), and
#: an accepted format must never land here just because a load failed once: the
#: accepted list is the decoder claim, this dict is the policy.
#:
#: Reasons are developer-facing English: the toast that shows them goes through
#: the i18n catalogue in a follow-up pass (``tr()`` keys, four locales), which
#: is why this task only ships the data, not the wording on screen.
REJECTED_SUFFIXES: dict[str, str] = {
    # Documents / page descriptions: rasterizing a page is not decoding a frame.
    ".pdf": (
        "PDF document: a page has to be rasterized, and the bundled Pillow "
        "registers a PDF writer only (no opener)."
    ),
    ".ps": (
        "PostScript: rasterizing needs a system Ghostscript, which is not a "
        "dependency of the app."
    ),
    ".eps": (
        "Encapsulated PostScript: same Ghostscript dependency as .ps -- no "
        "in-process rasterizer is shipped."
    ),
    # Data containers that hold pixels but are not pictures.
    ".h5": (
        "HDF5 data container: arbitrary scientific datasets, not a pixel "
        "frame (h5py reads arrays, not pictures)."
    ),
    ".hdf": "HDF5 data container (see .h5) -- datasets, not a frame.",
    ".fits": (
        "FITS astronomy container: HDU planes with own headers, not one frame "
        "(Pillow needs astropy, which is not a dependency)."
    ),
    ".fit": "FITS astronomy container (see .fits) -- not a single frame.",
    ".grib": (
        "GRIB weather container: needs the eccodes library, which is not a "
        "dependency."
    ),
    ".bufr": (
        "BUFR weather observation container: same eccodes dependency as .grib."
    ),
    ".iim": "IPTC/IIM metadata block -- no pixels in the file at all.",
    # Vector / metafile: no native pixel size to compare.
    ".wmf": (
        "Windows metafile (vector): rasterizing needs an external converter, "
        "so there is no frame to load."
    ),
    ".emf": (
        "Windows enhanced metafile (vector): no decoder for it is shipped."
    ),
    ".svg": (
        "SVG (vector): has to be rasterized at a chosen scale first (QtSvg), "
        "so the file has no native pixel size the tabs could compare."
    ),
    # Obsolete / media-bound still formats the audit keeps out.
    ".pcd": (
        "Kodak PhotoCD: obsolete physical-media format, outside the intake "
        "policy, and decode coverage depends on the Pillow build."
    ),
    ".palm": (
        "Palm bitmap: Pillow's Palm plugin is write-only on this stack (it "
        "registers no opener)."
    ),
    # Video: the app compares stills; motion has its own tab.
    ".mpeg": "Video container -- the comparison tabs take stills, not streams.",
    ".mpg": "Video container (see .mpeg) -- stills only.",
    # HDR / next-generation containers without a guaranteed decoder.
    ".heic": (
        "HEIC (Apple HEIF): Pillow cannot decode it, and libvips only when "
        "built with libheif -- acceptance would be machine-dependent."
    ),
    ".heif": (
        "HEIF container: same libheif build dependency as .heic, so the "
        "verdict would differ between distro and bundled builds."
    ),
    ".exr": (
        "OpenEXR: floating-point HDR frames; no decoder is installed here "
        "(no Pillow plugin, this libvips has no exr loader)."
    ),
    # Camera RAW: the file is sensor data plus an embedded preview.
    ".cr2": _RAW_REASON,
    ".cr3": _RAW_REASON,
    ".nef": _RAW_REASON,
    ".arw": _RAW_REASON,
    ".dng": _RAW_REASON,
    ".orf": _RAW_REASON,
    ".raf": _RAW_REASON,
    ".rw2": _RAW_REASON,
    ".srw": _RAW_REASON,
    ".pef": _RAW_REASON,
    ".mrw": _RAW_REASON,
    ".mef": _RAW_REASON,
    ".mos": _RAW_REASON,
    ".raw": (
        "Headerless RAW: no demosaicing (see .cr2), and libvips' raw loader "
        "needs caller-supplied geometry before any pixel exists."
    ),
}

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


def rejection_reason(path) -> str | None:
    """Why *path*'s format is refused, or ``None`` when the canon admits it.

    The one home for a self-explaining refusal: a toast, a drag-hint or a
    scanner can say "PDF document: ..." instead of "could not load the image".
    Lookup is by suffix only (case-insensitive) and never touches the
    filesystem, so it is safe on the drop-enter path.

    ``None`` means "the canon accepts this suffix"; an unknown non-image suffix
    (``.txt``) is also ``None`` because it is not a format decision at all.
    Suffix lists never overlap: group C in :data:`REJECTED_SUFFIXES` and the
    accepted set are disjoint by contract.
    """
    from pathlib import Path as _Path

    try:
        suffix = _Path(str(path)).suffix.lower()
    except Exception:
        return None
    if suffix in ACCEPTED_IMAGE_EXTENSIONS:
        return None
    return REJECTED_SUFFIXES.get(suffix)


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
