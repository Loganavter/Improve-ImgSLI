"""AVIF accepted end-to-end: DnD, dialog filter, folder scan, preview, full decode.

Before 2026-10-28 ``.avif`` decoded fine (Pillow and libvips both read it) but
was missing from ``shared.image_extensions.ACCEPTED_IMAGE_EXTENSIONS``. That
frozenset is the single gate for every entry point, so the *same* file opened
when handed to the loader directly and was rejected by DnD, the file-dialog
filter and the gallery folder scan. This module walks those entry points on
one real AVIF file instead of trusting the extension list.

Capability-skipped, not silently skipped: the probe is authored with Pillow,
so a build without the AVIF plugin cannot produce the fixture at all. The skip
names that exact condition (no AVIF plugin), never "this may be flaky".
"""

from __future__ import annotations

import pytest

# 640x400 stays under the 1024 px preview cap, so preview dimensions must
# match the source exactly.
PROBE_SIZE = (640, 400)
PROBE_RGB = (10, 20, 30)


def _avif_capable() -> bool:
    """Whether this Pillow build can both write and read AVIF."""
    try:
        from PIL import Image, features

        return bool(features.check("avif")) and ".avif" in Image.registered_extensions()
    except Exception:
        return False


requires_avif = pytest.mark.skipif(
    not _avif_capable(),
    reason=(
        "Pillow build has no AVIF plugin (features.check('avif') is False), "
        "so the probe file cannot be authored"
    ),
)


@pytest.fixture
def avif_probe(tmp_path):
    """A real AVIF file on disk -- the decoders are exercised, not mocked."""
    from PIL import Image

    path = tmp_path / "probe.avif"
    Image.new("RGB", PROBE_SIZE, PROBE_RGB).save(path, format="AVIF", quality=100)
    assert path.is_file() and path.stat().st_size > 0
    return path


@requires_avif
def test_avif_is_accepted_and_loadable(avif_probe, tmp_path):
    """The admission predicates must accept an AVIF file (and its uppercase form)."""
    from shared.image_extensions import is_accepted_image_path, is_loadable_image_path

    assert is_accepted_image_path(avif_probe) is True
    assert is_loadable_image_path(avif_probe) is True

    upper = tmp_path / "PROBE.AVIF"
    upper.write_bytes(avif_probe.read_bytes())
    assert is_accepted_image_path(upper) is True
    assert is_loadable_image_path(upper) is True


@requires_avif
def test_avif_appears_in_dialog_filter(avif_probe):
    """The file dialog must offer ``*.avif`` -- a hidden suffix is a bounce."""
    from shared.image_extensions import build_image_dialog_filter

    assert "*.avif" in build_image_dialog_filter()


@requires_avif
def test_avif_drop_mime_is_accepted(avif_probe, tmp_path):
    """A real local-file QMimeData carrying the AVIF is a valid image drop."""
    from PySide6.QtCore import QMimeData, QUrl

    from shared.image_extensions import has_image_urls

    text = tmp_path / "notes.txt"
    text.write_text("not an image")

    image_mime = QMimeData()
    image_mime.setUrls([QUrl.fromLocalFile(str(avif_probe))])
    assert has_image_urls(image_mime) is True

    text_mime = QMimeData()
    text_mime.setUrls([QUrl.fromLocalFile(str(text))])
    assert has_image_urls(text_mime) is False


@requires_avif
def test_avif_dimensions_and_format_are_read(avif_probe):
    """Header reads (card size / format badge) work without a full decode."""
    from shared.image_processing.progressive_loader import (
        get_image_dimensions,
        get_image_format_info,
    )

    assert get_image_dimensions(str(avif_probe)) == PROBE_SIZE

    format_name, _is_progressive, _has_alpha = get_image_format_info(str(avif_probe))
    assert format_name == "AVIF"


@requires_avif
def test_avif_preview_image_loads(avif_probe):
    """The display tier returns a non-null QImage at the source size."""
    from shared.image_processing.progressive_loader import load_preview_image

    preview = load_preview_image(str(avif_probe))
    assert preview is not None
    assert preview.isNull() is False
    assert (preview.width(), preview.height()) == PROBE_SIZE


@requires_avif
def test_avif_is_found_by_folder_scan(avif_probe):
    """A folder drop must list the AVIF card, next to other images only."""
    from tabs.image_gallery.services.folder_scanner import scan_folder

    (avif_probe.parent / "notes.txt").write_text("not an image")

    items = scan_folder(avif_probe.parent)
    assert [item.name for item in items] == ["probe.avif"]


@requires_avif
def test_full_resolution_pillow_decode_reads_avif(avif_probe):
    """The full-res path (``TiledPixelStore``/pyramid use ``PIL.Image.open``).

    A card that appears and then fails on open (the preview tier uses libvips
    when it can stream, the full tier always falls back to Pillow) is the
    worse outcome; decode the whole surface here and check real pixels.
    """
    from PIL import Image

    with Image.open(avif_probe) as img:
        assert img.size == PROBE_SIZE
        rgba = img.convert("RGBA")
        rgba.load()
        assert rgba.size == PROBE_SIZE
        assert rgba.mode == "RGBA"

    cx, cy = PROBE_SIZE[0] // 2, PROBE_SIZE[1] // 2
    r, g, b, a = rgba.getpixel((cx, cy))
    assert a == 255
    # AVIF is lossy by default; a flat color must still land close. Compare
    # per channel with ``max`` -- tuple ``<=`` is lexicographic and would let
    # a large deviation through on the last channel.
    deviation = max(
        abs(r - PROBE_RGB[0]), abs(g - PROBE_RGB[1]), abs(b - PROBE_RGB[2])
    )
    assert deviation <= 8, (r, g, b)
