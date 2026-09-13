"""Autocrop debug must always end with an explicit verdict.

Regression for "неинформативный дебаг": the log said `crop_service=no`
but never stated whether autocrop was actually applied or skipped.
Every `TiledPixelStore.from_path` decode path (streaming / ndarray / PIL)
must emit exactly one `[autocrop-debug] ... verdict=SKIP|APPLIED ...` line
with the reason (disabled vs probe-found-no-box).
"""

import logging

from PIL import Image

from shared.image_processing.autocrop import CropService
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def _save(path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def _bordered_image():
    canvas = Image.new("RGBA", (200, 160), (0, 0, 0, 255))
    canvas.paste(Image.new("RGBA", (120, 80), (200, 180, 160, 255)), (40, 40))
    return canvas


def _enable_autocrop_debug(monkeypatch, caplog):
    monkeypatch.setenv("IMGSLI_AUTOCROP_DEBUG", "1")
    caplog.set_level(logging.DEBUG, logger="ImproveImgSLI")


def test_disabled_service_logs_skip_verdict(tmp_path, monkeypatch, caplog):
    """crop_service=None → verdict=SKIP reason=disabled (not silence)."""
    _enable_autocrop_debug(monkeypatch, caplog)
    path = _save(tmp_path / "plain.png", _bordered_image())

    store = TiledPixelStore.from_path(path, crop_service=None)
    try:
        assert store.size == (200, 160)  # nothing cropped
    finally:
        store.close()

    verdicts = [r for r in caplog.text.splitlines() if "verdict=" in r]
    assert verdicts, f"no verdict line emitted:\n{caplog.text}"
    assert any("verdict=SKIP" in v and "disabled" in v for v in verdicts), (
        f"expected SKIP/disabled verdict:\n" + "\n".join(verdicts)
    )


def test_enabled_bordered_logs_applied_verdict(tmp_path, monkeypatch, caplog):
    """Real black border + service → verdict=APPLIED with box and dims."""
    _enable_autocrop_debug(monkeypatch, caplog)
    path = _save(tmp_path / "bordered.png", _bordered_image())

    store = TiledPixelStore.from_path(path, crop_service=CropService())
    try:
        w, h = store.size
        assert (w, h) != (200, 160)
    finally:
        store.close()

    assert any("verdict=APPLIED" in v for v in caplog.text.splitlines()), (
        f"expected APPLIED verdict:\n{caplog.text}"
    )


def test_enabled_borderless_logs_skip_no_box(tmp_path, monkeypatch, caplog):
    """Service present but nothing to trim → verdict=SKIP reason=no box."""
    _enable_autocrop_debug(monkeypatch, caplog)
    solid = Image.new("RGBA", (120, 90), (200, 180, 160, 255))
    path = _save(tmp_path / "solid.png", solid)

    store = TiledPixelStore.from_path(path, crop_service=CropService())
    try:
        assert store.size == (120, 90)
    finally:
        store.close()

    verdicts = [r for r in caplog.text.splitlines() if "verdict=" in r]
    assert any("verdict=SKIP" in v and "no box" in v for v in verdicts), (
        f"expected SKIP/no-box verdict:\n" + "\n".join(verdicts)
    )
