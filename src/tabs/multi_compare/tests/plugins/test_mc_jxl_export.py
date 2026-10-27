"""Multi Compare export: every offered format really reaches the file.

The defect this pins (red-before, measured on the base commit ``f3b91cf83``)::

    tabs.multi_compare.services.image_export.save_composite(img, {\"format\": \"JXL\"})
    -> KeyError('JXL')
    ... same call with {\"format\": \"PNG\"} -> file written

The tab handed the format straight to ``Pillow``, which has no JXL plugin, so
the save failed *after* the user had configured the whole export (the format
was offered in the shared dialog, which the single-view tab could satisfy
through its own private ``imagecodecs`` branch). Both save paths now go through
``shared.image_processing.format_capability.encode``.

These stay in the tab's own suite (not ``tests/contracts/``): they exercise
this tab's save path, and root tests must not deep-import a tab's internals —
see ``tests/contracts/test_root_tests_no_tab_internals_leak.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from shared.image_processing.format_capability import (
    suffix_for_format,
    writable_formats,
)
from tabs.multi_compare.services.image_export import save_composite

#: Formats the multi-compare path must round-trip on any stack.
_BASE_FORMATS = ["PNG", "JPEG", "WEBP", "BMP", "TIFF"]


def _options(tmp_path, image_format: str, name: str) -> dict:
    return {
        "output_dir": str(tmp_path),
        "file_name": name,
        "format": image_format,
        "quality": 95,
        "background_color": (255, 255, 255, 255),
    }


@pytest.mark.parametrize("image_format", _BASE_FORMATS)
def test_save_composite_round_trips(image_format, tmp_path):
    """Control: the base formats were fine before and must stay fine."""
    image = Image.new("RGBA", (16, 12), (40, 80, 120, 255))

    output = save_composite(image, _options(tmp_path, image_format, "roundtrip"))

    assert Path(output).name == f"roundtrip{suffix_for_format(image_format)}"
    with Image.open(output) as saved:
        assert saved.size == (16, 12)
        # JPEG/WEBP are lossy, so the flat colour is compared with a tolerance;
        # the claim is that the frame reached the file intact.
        red, green, blue = saved.convert("RGB").getpixel((0, 0))
        assert (abs(red - 40), abs(green - 80), abs(blue - 120)) <= (8, 8, 8)


def test_save_composite_writes_jxl_that_reads_back(tmp_path):
    """The regression: JXL used to raise ``KeyError('JXL')`` here."""
    if "JXL" not in writable_formats():
        pytest.skip(
            "no JXL encoder on this machine (imagecodecs/libjxl absent), so the "
            "format is correctly not offered; the end-to-end claim needs a "
            "stack that has it"
        )

    image = Image.new("RGBA", (16, 12), (40, 80, 120, 255))

    output = save_composite(image, _options(tmp_path, "JXL", "jxl"))

    assert Path(output).name == "jxl.jxl"
    with open(output, "rb") as handle:
        assert handle.read(2) == b"\xff\x0a", "not a JXL codestream"
    try:
        import imagecodecs

        assert imagecodecs.imread(output).shape[:2] == (12, 16)
    except ImportError:  # a PIL plugin provides the decoder instead
        with Image.open(output) as saved:
            assert saved.size == (16, 12)


def test_save_composite_refusal_names_the_missing_backend(tmp_path, monkeypatch):
    """When JXL is not offered, the save says why instead of ``KeyError``.

    Simulates a build without the JXL backend (the state of the machine this
    test was written on, where ``imagecodecs`` is genuinely absent) and checks
    the user-facing message rather than a raw Pillow key error.
    """
    from shared.image_processing import format_capability as caps

    monkeypatch.setattr(caps, "_jxl_backend", lambda: None)
    monkeypatch.setattr(
        caps, "_pillow_writable_formats", lambda: frozenset(_BASE_FORMATS)
    )

    image = Image.new("RGBA", (16, 12), (40, 80, 120, 255))
    with pytest.raises(ValueError) as excinfo:
        save_composite(image, _options(tmp_path, "JXL", "unavailable"))

    message = str(excinfo.value)
    assert "JXL" in message and "imagecodecs" in message
    assert not list(Path(tmp_path).glob("unavailable*")), "a refused save wrote a file"
