"""Camera metrics worker (services/camera_metrics + controller delivery).

Keys must match exactly what the quick-look camera report reads
(sharpness / exposure / clipping_pct); unreadable sources land nothing so
rows keep honest "not measured" instead of fabricated values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tabs.image_gallery.services.camera_metrics import (
    measure_camera_metrics,
    run_camera_metrics_sync,
)


def _paint(path: Path, kind: str) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64))
    if kind == "gray":
        img = Image.new("RGB", (64, 64), (128, 128, 128))
    elif kind == "split":
        # Mid-gray field with a 16x16 pure-white square: 6.25% clipped.
        img = Image.new("RGB", (64, 64), (128, 128, 128))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 15], fill=(255, 255, 255))
    elif kind == "checker":
        draw = ImageDraw.Draw(img)
        for y in range(0, 64, 8):
            for x in range(0, 64, 8):
                if (x + y) % 16 == 0:
                    draw.rectangle([x, y, x + 7, y + 7], fill=(255, 255, 255))
    img.save(path)
    return path


def test_flat_gray_exposure_half_no_clipping(tmp_path: Path) -> None:
    p = _paint(tmp_path / "gray.png", "gray")
    out = measure_camera_metrics(p)
    assert out["exposure"] == pytest.approx(128 / 255)
    assert out["clipping_pct"] == 0.0
    assert out["sharpness"] == 0.0


def test_clipping_counts_extreme_pixels(tmp_path: Path) -> None:
    p = _paint(tmp_path / "split.png", "split")
    out = measure_camera_metrics(p)
    assert out["clipping_pct"] == pytest.approx(100 * 256 / 4096)
    assert out["exposure"] == pytest.approx((128 * (4096 - 256) + 255 * 256) / 4096 / 255)


def test_checker_sharper_than_flat(tmp_path: Path) -> None:
    flat = measure_camera_metrics(_paint(tmp_path / "flat.png", "gray"))
    sharp = measure_camera_metrics(_paint(tmp_path / "checker.png", "checker"))
    assert sharp["sharpness"] > flat["sharpness"]


def test_unreadable_is_fail_closed(tmp_path: Path) -> None:
    assert measure_camera_metrics(tmp_path / "nope.png") == {}


def test_worker_entry_keys_by_path(tmp_path: Path) -> None:
    from types import SimpleNamespace

    a = SimpleNamespace(path=_paint(tmp_path / "a.png", "gray"))
    out = run_camera_metrics_sync([a])
    assert set(out[str(a.path)]) == {"sharpness", "exposure", "clipping_pct"}


def test_camera_ready_delivery(tmp_path: Path) -> None:
    """Delivery lands scalars by path + refreshes cards and open overlay."""
    from PySide6.QtCore import QThreadPool

    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.tests.runtime.test_gallery_truth import (
        _FakeQuickLookOverlay,
        _FidelityWidgetStub,
    )

    a = GalleryItem(path=tmp_path / "a.jpg", mtime_ns=1, metrics={})
    b = GalleryItem(path=tmp_path / "b.jpg", mtime_ns=2, metrics={})
    overlay = _FakeQuickLookOverlay()
    widget = _FidelityWidgetStub(overlay=overlay)
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=None)
    ctrl.state.items = [a, b]

    delivered = {"sharpness": 210.0, "exposure": 0.48, "clipping_pct": 1.2}
    ctrl._on_camera_metrics_ready({str(a.path): dict(delivered)}, None)

    for k, v in delivered.items():
        assert a.metrics[k] == v
    assert all(k not in b.metrics for k in delivered)
    assert overlay.refreshed == [a]
    assert a in widget.refreshed_cards


def test_camera_ready_stale_gen_dropped(tmp_path: Path) -> None:
    from PySide6.QtCore import QThreadPool

    from tabs.image_gallery.controller import GalleryController
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.tests.runtime.test_gallery_truth import _FidelityWidgetStub

    a = GalleryItem(path=tmp_path / "a.jpg", mtime_ns=1, metrics={})
    widget = _FidelityWidgetStub()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=None)
    ctrl.state.items = [a]
    ctrl._folder_gen = 7
    ctrl._on_camera_metrics_ready({str(a.path): {"sharpness": 1.0}}, 6)
    assert a.metrics == {}
