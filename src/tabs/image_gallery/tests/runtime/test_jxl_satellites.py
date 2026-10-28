"""JXL "satellites": card size, properties panel, triage metrics.

Accepting ``.jxl`` in ``shared.image_extensions`` is only half the promise.
Three surfaces read a file WITHOUT going through the canvas, and each was wired
to Pillow (or to an ``imagecodecs``-gated branch) alone:

* ``progressive_loader.get_image_dimensions`` parsed the codestream SizeHeader
  only INSIDE ``if JXL_SUPPORTED``. The header parse needs no codec, so a build
  without ``imagecodecs`` — exactly the profile where the answer is free —
  reported no size at all.
* ``plugins.image_properties.service._read_source_info`` had one path,
  Pillow, so JXL landed in ``read_error`` on EVERY profile.
* the gallery triage (dHash, HSV embedding, Laplacian sharpness, EXIF bit)
  decodes through ``decode_cache``, which also only used Pillow: every JXL
  scored a zero hash and a zero embedding — "corrupt" for an accepted file.

Red-before on the parent commit (this environment: no ``imagecodecs``, libvips
with libjxl — the "codec-missing" profile)::

    get_image_dimensions(jxl)      -> None            (header alone gives (64, 48))
    _read_source_info(jxl)         -> {'read_error': "cannot identify image file ..."}
    decode_image(jxl)              -> None
    compute_phash(jxl)             -> 0
    embedding(jxl)                 -> [0.0] * 192
    _sharpness(jxl)                -> None

Nothing here may depend on ``imagecodecs`` being installed: the codec-absent
profile is asserted explicitly (``JXL_SUPPORTED`` monkeypatched False), and the
codec-present profile runs only where the module really exists.
"""

from __future__ import annotations

import pytest

FIXTURE_NAME = "jxl-probe.jxl"
#: ``tests/fixtures/formats/jxl-probe.jxl`` — 64x48, two colours by half.
FIXTURE_DIMS = (64, 48)
LEFT_RGB = (22, 120, 200)
RIGHT_RGB = (240, 90, 30)

try:  # the "codec present" profile is conditional, never assumed
    import imagecodecs  # noqa: F401

    HAS_IMAGECODECS = True
except Exception:  # pragma: no cover - profile-dependent
    HAS_IMAGECODECS = False


def _fixture_path(name: str = FIXTURE_NAME):
    """Locate a committed format fixture from any cwd."""
    from pathlib import Path

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tests" / "fixtures" / "formats" / name
        if candidate.is_file():
            return candidate
    raise AssertionError(f"format fixture {name!r} not found above {__file__}")


@pytest.fixture
def jxl_probe():
    return _fixture_path()


def _host_can_decode_jxl_without_the_codec() -> bool:
    """Whether THIS host decodes the probe with ``imagecodecs`` DISABLED.

    That is the profile every assertion below runs in (``_no_codec_profile``
    pins ``JXL_SUPPORTED = False``), so the only decoder left is a libvips build
    with libjxl — the profile this suite was written on.

    Measured 2026-10-28 on a host whose pyvips 3.1.1 has NO JPEG-XL loader
    (``Image.new_from_file``: "unable to load from file"): there the codec-less
    profile cannot decode anything, two tests stayed red on ``main``, and a red
    tier hides real regressions. A test that claims "triage measures JXL instead
    of scoring zero" is provable only where something can decode it, so this
    asks the app's own capability probe rather than assuming one.
    """
    try:
        from shared.image_processing import progressive_loader

        return progressive_loader.pyvips_can_stream(_fixture_path())
    except Exception:
        return False


@pytest.fixture
def png_probe(tmp_path):
    """Same picture, Pillow-native: the regression side of every check."""
    from PIL import Image

    path = tmp_path / "probe.png"
    image = Image.new("RGB", FIXTURE_DIMS, LEFT_RGB)
    right = Image.new("RGB", (FIXTURE_DIMS[0] // 2, FIXTURE_DIMS[1]), RIGHT_RGB)
    image.paste(right, (FIXTURE_DIMS[0] // 2, 0))
    image.save(path, format="PNG")
    return path


@pytest.fixture(autouse=True)
def _cold_caches():
    """Triage caches are keyed by (path, mtime_ns, size) — one test's warm
    frame would hide the next test's decode path."""
    from tabs.image_gallery.services import clustering, decode_cache, mode

    decode_cache.clear()
    clustering.clear_signature_cache()
    mode.clear_sharpness_cache()
    mode.clear_exif_cache()
    yield
    decode_cache.clear()
    clustering.clear_signature_cache()
    mode.clear_sharpness_cache()
    mode.clear_exif_cache()


def _no_codec_profile(monkeypatch):
    """Pin the codec-absent profile: the branch under test must not need it."""
    from shared.image_processing import progressive_loader

    monkeypatch.setattr(progressive_loader, "JXL_SUPPORTED", False, raising=True)
    return progressive_loader


# -- 1. dimensions ---------------------------------------------------------


def test_dimensions_need_no_jxl_codec(jxl_probe, monkeypatch):
    """The SizeHeader is a header parse: no imagecodecs, still (64, 48)."""
    loader = _no_codec_profile(monkeypatch)

    # The free answer the gated branch used to hide.
    assert loader.read_jxl_header_dimensions(str(jxl_probe)) == FIXTURE_DIMS
    assert loader.get_image_dimensions(str(jxl_probe)) == FIXTURE_DIMS


def test_format_info_survives_a_missing_codec(jxl_probe, monkeypatch):
    loader = _no_codec_profile(monkeypatch)

    format_name, progressive, has_alpha = loader.get_image_format_info(str(jxl_probe))
    assert (format_name, progressive, has_alpha) == ("JXL", False, False)


@pytest.mark.skipif(
    not HAS_IMAGECODECS,
    reason="imagecodecs is not installed, so the full-decode branch cannot run",
)
def test_dimensions_are_the_same_with_the_codec(jxl_probe, monkeypatch):
    """The restructure must not change the answer where a codec exists."""
    from shared.image_processing import progressive_loader

    monkeypatch.setattr(progressive_loader, "JXL_SUPPORTED", True, raising=True)
    assert progressive_loader.get_image_dimensions(str(jxl_probe)) == FIXTURE_DIMS


def test_unreadable_jxl_still_reports_nothing(tmp_path, monkeypatch):
    """Header-first is not header-guessing: garbage keeps producing None."""
    loader = _no_codec_profile(monkeypatch)
    broken = tmp_path / "broken.jxl"
    broken.write_bytes(b"not a jxl codestream at all" * 4)

    assert loader.get_image_dimensions(str(broken)) is None


def test_dimensions_and_format_survive_neither_backend(jxl_probe, monkeypatch):
    """No imagecodecs AND no libvips JXL loader: the header still answers.

    The point of the fix is backend-independence — every install combination
    must produce the same card size, and the properties panel must degrade to
    "no colour mode" rather than to a read error.
    """
    loader = _no_codec_profile(monkeypatch)
    monkeypatch.setattr(loader, "pyvips_can_stream", lambda *a, **k: False, raising=True)

    assert loader.get_image_dimensions(str(jxl_probe)) == FIXTURE_DIMS

    from plugins.image_properties.service import _read_source_info

    info = _read_source_info(jxl_probe)
    assert "read_error" not in info
    assert info["dimensions"] == FIXTURE_DIMS
    # Nothing decoded the pixels, so the mode row stays absent.
    assert "mode" not in info


# -- 2. properties panel ---------------------------------------------------


def test_properties_report_jxl_without_read_error(jxl_probe, monkeypatch):
    """The panel must describe the file, not Pillow's missing plugin."""
    _no_codec_profile(monkeypatch)
    from plugins.image_properties.service import _read_source_info

    info = _read_source_info(jxl_probe)

    assert "read_error" not in info
    assert info["format"] == "JXL"
    assert info["dimensions"] == FIXTURE_DIMS
    # Mode comes from a real decode (header band count here), never assumed.
    if _host_can_decode_jxl_without_the_codec():
        assert info.get("mode") in ("L", "LA", "RGB", "RGBA")
    else:
        # No decoder on this host: the honest answer is NO row, never a guess
        # (the panel renders an absent key as no row — see the service docstring).
        assert "mode" not in info
    # Exotic metadata was never read, so the keys are ABSENT, not invented.
    for absent in ("dpi", "color_profile", "exif"):
        assert absent not in info


def test_properties_rows_carry_the_real_size(jxl_probe, monkeypatch):
    """End of the pipe: the rows the dialog draws."""
    _no_codec_profile(monkeypatch)
    from plugins.image_properties.service import build_image_properties

    text = build_image_properties(path=jxl_probe).as_plain_text(lambda key: key)

    assert "64 x 48 px" in text
    assert "Format: JXL" in text
    assert "Read error" not in text


def test_properties_png_is_unchanged(png_probe, monkeypatch):
    """Regression: the Pillow path keeps precedence and its own metadata."""
    _no_codec_profile(monkeypatch)
    from plugins.image_properties.service import _read_source_info

    info = _read_source_info(png_probe)

    assert "read_error" not in info
    assert info["format"] == "PNG"
    assert info["dimensions"] == FIXTURE_DIMS
    assert info["mode"] == "RGB"


def test_properties_unreadable_accepted_file_keeps_the_error(tmp_path, monkeypatch):
    """The fallback must not launder an unreadable file into a clean panel."""
    _no_codec_profile(monkeypatch)
    from plugins.image_properties.service import _read_source_info

    broken = tmp_path / "broken.jxl"
    broken.write_bytes(b"not a jxl codestream at all" * 4)

    info = _read_source_info(broken)
    assert info.get("read_error")
    assert "dimensions" not in info


# -- 3. triage -------------------------------------------------------------


@pytest.mark.skipif(
    not _host_can_decode_jxl_without_the_codec(),
    reason="this host has no JPEG-XL decoder (libvips without libjxl, imagecodecs without JXL) — "
    "measurement cannot be proven here",
)
def test_triage_measures_jxl_instead_of_scoring_zero(jxl_probe, monkeypatch):
    """phash / embedding / sharpness describe real pixels, not the sentinel."""
    _no_codec_profile(monkeypatch)
    from tabs.image_gallery.services import clustering, decode_cache, mode

    frame = decode_cache.decode_image(jxl_probe)
    assert frame is not None
    assert frame.size == FIXTURE_DIMS

    # 0 hash + zero vector is how clustering spells "corrupt" — the defect.
    assert clustering.compute_phash(jxl_probe) != 0
    assert clustering.embedding(jxl_probe) != [0.0] * 192
    sharpness = mode._sharpness(jxl_probe)
    assert sharpness is not None and sharpness > 0

    # EXIF is genuinely unknown on the fallback decode: the frame came from a
    # backend that never parsed the container, so None ("not measured") is the
    # honest bit — not False ("measured: no EXIF").
    assert decode_cache.exif_present(jxl_probe) is None


def test_triage_png_is_unchanged(png_probe, monkeypatch):
    """Regression: the Pillow decode still wins for formats it supports."""
    _no_codec_profile(monkeypatch)
    from tabs.image_gallery.services import clustering, decode_cache, mode

    assert decode_cache.decode_image(png_probe) is not None
    assert clustering.compute_phash(png_probe) != 0
    assert clustering.embedding(png_probe) != [0.0] * 192
    assert mode._sharpness(png_probe) is not None
    assert decode_cache.exif_present(png_probe) is False


def test_undecodable_file_is_unmeasured_not_a_zero_measurement(jxl_probe, monkeypatch):
    """No backend at all: callers get an explicit None, never a fake reading."""
    _no_codec_profile(monkeypatch)
    from shared.image_processing import bounded_frame

    # Block the fallback decoder — this is the "neither Pillow nor libvips nor
    # imagecodecs can read it" profile.
    monkeypatch.setattr(
        bounded_frame, "load_bounded_frame", lambda *a, **k: None, raising=True
    )

    from tabs.image_gallery.services import clustering, decode_cache, mode

    assert decode_cache.decode_image(jxl_probe) is None
    assert decode_cache.exif_present(jxl_probe) is None
    assert mode._sharpness(jxl_probe) is None

    # The hash/vector sentinels still arrive (callers' existing fail-closed
    # contract), but only together with a None frame — which is what makes
    # "not measured" decidable at the call site instead of a silent zero.
    assert decode_cache.decode_image(jxl_probe) is None
    assert clustering.compute_phash(jxl_probe) == 0
    assert clustering.embedding(jxl_probe) == [0.0] * 192
