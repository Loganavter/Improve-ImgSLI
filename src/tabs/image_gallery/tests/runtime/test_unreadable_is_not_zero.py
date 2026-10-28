"""An unreadable file is UNMEASURED, not a measured zero (and not the reverse).

The marker exists: ``decode_cache.decode_image`` and ``exif_present`` return
``None`` for a file no backend could parse. Two call sites collapsed it and both
directions of the mistake were visible on 2026-10-28:

* ``mode._has_exif``/``exif_for`` returned ``False`` via ``bool(None)`` — the panel
  claimed "measured: no EXIF" about a file nobody measured. Fixed to a three-state
  answer, and ``select_mode`` now requires ``is True`` (an unmeasured file never
  proves the folder came from a camera).
* ``cluster_items`` inferred "corrupt" from ``phash == 0 and embedding == zeros``.
  That is also the signature of an **all-black image** — a perfect uniform picture
  hashes to 0 and its HSV value channel is 0 everywhere — so a readable file was
  dropped from its own series. Readable-ness is now the DECODE's answer.

What was already honest, and is pinned here so nobody "fixes" it: the axis/dot read
path reports ``status="gap"`` with ``value=None`` for an undecodable file, never a
zero band.
"""

from __future__ import annotations

import pathlib

import pytest
from PIL import Image

from tabs.image_gallery.analysis import read as analysis_read
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import clustering, decode_cache, mode


@pytest.fixture
def corrupt(tmp_path) -> pathlib.Path:
    """A PNG header with no image data: no shipped backend can decode it."""
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    return path


@pytest.fixture
def all_black(tmp_path) -> pathlib.Path:
    """Readable, uniform, and — the point — a zero hash with a zero embedding."""
    path = tmp_path / "black.png"
    Image.new("RGB", (64, 64), (0, 0, 0)).save(path)
    return path


def test_the_marker_is_none_for_a_file_no_backend_reads(corrupt):
    assert decode_cache.decode_image(corrupt) is None
    assert decode_cache.exif_present(corrupt) is None


def test_exif_presence_is_three_state(corrupt, all_black):
    assert mode.exif_for(corrupt) is None, (
        "nobody parsed this file; False would claim a measurement"
    )
    assert mode.exif_for(all_black) is False, (
        "a readable JPEG-less PNG was parsed: no EXIF is a MEASURED answer"
    )


def test_an_all_black_image_is_readable_despite_its_zero_signature(all_black):
    phash, embedding = clustering.signature_for(all_black)

    assert phash == 0 and set(embedding) == {0.0}, (
        "the signature of a uniform picture looks exactly like the old 'corrupt' "
        "inference — which is why the inference was wrong"
    )
    assert decode_cache.decode_image(all_black) is not None, (
        "the decode is what decides readable-ness"
    )


def test_cluster_items_keeps_the_readable_black_frame_and_drops_the_corrupt_one(
    all_black, corrupt, tmp_path
):
    """Two identical black frames have to form a series; the corrupt one cannot."""
    sibling = tmp_path / "black2.png"
    Image.new("RGB", (64, 64), (0, 0, 0)).save(sibling)

    items = [
        GalleryItem(path=all_black, mtime_ns=1),
        GalleryItem(path=sibling, mtime_ns=1),
        GalleryItem(path=corrupt, mtime_ns=1),
    ]
    series = clustering.cluster_items(items)

    grouped = {str(member.path) for s in series for member in s.members}
    assert str(all_black) in grouped and str(sibling) in grouped, (
        "two byte-identical readable frames must cluster; the old zero-hash "
        "inference excluded them as corrupt"
    )
    assert str(corrupt) not in grouped, "an undecodable file belongs in no series"


def test_the_dot_read_path_reports_a_gap_not_a_zero(corrupt):
    item = GalleryItem(path=corrupt, mtime_ns=1)

    values = analysis_read.read_axes(item, domain="algorithms", axes=("sharpness", "noise"))

    assert values, "the reader answers one row per requested axis"
    for value in values:
        assert value.status == "gap"
        assert value.value is None
