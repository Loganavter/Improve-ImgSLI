"""Quick-look QLabel fallback zoom tests (no-GPU path interaction).

The raster fallback label (``preview._populate_preview_label``) used to
have zero zoom: any canvas miss left wheel/LMB dead. ``preview_label_zoom``
gives it cursor-anchored wheel zoom + drag pan with the same pure helpers
as the canvas (``preview_zoom.wheel_zoom_pan/drag_pan``). All offscreen-safe
(QPixmap/QLabel ops only, never RHI).
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look.preview import (
    _populate_preview_label,
    _rescale_preview_to_host,
)
from tabs.image_gallery.ui.quick_look.preview_label_zoom import (
    label_move,
    label_press,
    label_release,
    label_wheel,
    reset_label_zoom,
    zoomed_label_pixmap,
)


def _png(tmp_path: Path, name: str, color: str = "#3a6ea5", w: int = 800, h: int = 600) -> Path:
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _split_png(tmp_path: Path) -> Path:
    """Left-half dark / right-half light — pan shifts are pixel-visible."""
    from PySide6.QtGui import QPainter

    pm = QPixmap(400, 300)
    painter = QPainter(pm)
    painter.fillRect(0, 0, 200, 300, QColor("#112233"))
    painter.fillRect(200, 0, 200, 300, QColor("#ddeeff"))
    painter.end()
    p = tmp_path / "split.png"
    assert pm.save(str(p), "PNG")
    return p


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent
    return ov


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


def _shown(ov) -> bytes:
    pm = ov._preview_label.pixmap()
    assert pm is not None and not pm.isNull()
    img = pm.toImage()
    assert (img.width(), img.height()) == (pm.width(), pm.height())
    return bytes(img.constBits())


def test_zoomed_label_pixmap_sizes(qtbot):
    """1.0x contain-fits the slot; zoomed crops stay slot-sized."""
    from PySide6.QtGui import QPainter

    full = QPixmap(100, 50)
    full.fill(QColor("#112233"))
    painter = QPainter(full)
    painter.fillRect(0, 0, 50, 50, QColor("#aabbcc"))
    painter.end()
    out = zoomed_label_pixmap(full, 200, 100, 1.0)
    assert out is not None and (out.width(), out.height()) == (200, 100)
    z2 = zoomed_label_pixmap(full, 200, 100, 2.0)
    assert z2 is not None and (z2.width(), z2.height()) == (200, 100)
    assert bytes(z2.toImage().constBits()) != bytes(out.toImage().constBits())
    assert zoomed_label_pixmap(full, 0, 100, 1.0) is None
    null = QPixmap()
    assert zoomed_label_pixmap(null, 200, 100, 2.0) is None


def test_zoomed_label_pixmap_pan_shifts_crop(qtbot, tmp_path):
    """Same zoom, different pan → different crop (no neighbor smear)."""
    from PySide6.QtGui import QPainter

    full = QPixmap(100, 50)
    full.fill(QColor("#112233"))
    painter = QPainter(full)
    painter.fillRect(0, 0, 50, 50, QColor("#aabbcc"))
    painter.end()
    a = zoomed_label_pixmap(full, 200, 100, 2.0, 0.0, 0.0)
    b = zoomed_label_pixmap(full, 200, 100, 2.0, 0.5, 0.0)
    assert a is not None and b is not None
    assert bytes(a.toImage().constBits()) != bytes(b.toImage().constBits())


def test_label_wheel_zooms_and_floor_snaps(qtbot, tmp_path):
    """Wheel in zooms the fallback pixmap in-slot; hard out snaps to 1.0."""
    ov = _make_overlay(qtbot)
    _populate_preview_label(ov, _item(_png(tmp_path, "z.png")))
    QApplication.processEvents()
    base = _shown(ov)
    assert ov._label_zoom == 1.0

    assert label_wheel(ov, 240, 0.5, 0.5) is True
    assert ov._label_zoom > 1.0
    zoomed = _shown(ov)
    assert zoomed != base, "zoomed crop must differ from the fit pixmap"

    assert label_wheel(ov, -10000, 0.5, 0.5) is True
    assert ov._label_zoom == 1.0
    assert (ov._label_pan_x, ov._label_pan_y) == (0.0, 0.0)
    ov.hide()


def test_label_wheel_noop_without_preview(qtbot):
    """No stashed pixmap (or epsilon tick) → False, state untouched."""
    ov = _make_overlay(qtbot)
    assert label_wheel(ov, 240, 0.5, 0.5) is False
    assert ov._label_zoom == 1.0
    assert label_wheel(SimpleNamespace(_preview_full=None), 0.0001, 0.5, 0.5) is False
    ov.hide()


def test_label_drag_pans_only_when_zoomed(qtbot, tmp_path):
    """LMB drag at 1.0x is a no-op; zoomed it pans and repaints."""
    ov = _make_overlay(qtbot)
    _populate_preview_label(ov, _item(_split_png(tmp_path)))
    QApplication.processEvents()

    assert label_press(ov, 10.0, 10.0, Qt.MouseButton.LeftButton) is False
    assert ov._label_drag is None

    assert label_wheel(ov, 480, 0.5, 0.5) is True
    before = _shown(ov)
    assert label_press(ov, 50.0, 50.0, Qt.MouseButton.LeftButton) is True
    w, h = max(1, ov._preview_label.width()), max(1, ov._preview_label.height())
    assert label_move(ov, 150.0, 50.0, w, h) is True
    assert _shown(ov) != before
    label_release(ov)
    assert ov._label_drag is None
    assert label_move(ov, 160.0, 50.0, w, h) is False
    ov.hide()


def test_populate_resets_label_zoom(qtbot, tmp_path):
    """New image → whole-frame view (canvas set_source parity)."""
    ov = _make_overlay(qtbot)
    _populate_preview_label(ov, _item(_png(tmp_path, "a.png", "#c0392b")))
    QApplication.processEvents()
    assert label_wheel(ov, 480, 0.5, 0.5) is True
    assert ov._label_zoom > 1.0
    _populate_preview_label(ov, _item(_png(tmp_path, "b.png", "#3a6ea5")))
    QApplication.processEvents()
    assert ov._label_zoom == 1.0
    assert (ov._label_pan_x, ov._label_pan_y) == (0.0, 0.0)
    assert ov._label_drag is None
    ov.hide()


def test_reset_label_zoom_never_raises():
    reset_label_zoom(SimpleNamespace())
    reset_label_zoom(None)


def test_overlay_eventfilter_routes_label_wheel(qtbot, tmp_path):
    """Wheel over the fallback label is consumed once zoom changes."""
    ov = _make_overlay(qtbot)
    _populate_preview_label(ov, _item(_png(tmp_path, "e.png")))
    QApplication.processEvents()
    accepted: list = []

    class _Wheel:
        def type(self):  # noqa: N802
            return QEvent.Type.Wheel

        def position(self):  # noqa: N802
            return QPointF(100.0, 80.0)

        def angleDelta(self):  # noqa: N802
            return QPoint(0, 240)

        def accept(self):  # noqa: N802
            accepted.append(True)

    assert ov.eventFilter(ov._preview_label, _Wheel()) is True
    assert accepted == [True]
    assert ov._label_zoom > 1.0
    ov.hide()


def test_overlay_eventfilter_ignores_wheel_without_preview(qtbot):
    """Empty label → filter declines (old propagation preserved)."""
    ov = _make_overlay(qtbot)

    class _Wheel:
        def type(self):  # noqa: N802
            return QEvent.Type.Wheel

        def position(self):  # noqa: N802
            return QPointF(10.0, 10.0)

        def angleDelta(self):  # noqa: N802
            return QPoint(0, 240)

        def accept(self):  # noqa: N802
            raise AssertionError("must not accept without a preview")

    assert ov.eventFilter(ov._preview_label, _Wheel()) is False
    ov.hide()


def test_rescale_applies_zoom_cache_key(qtbot, tmp_path):
    """Same size + different zoom must repaint (no stale fit pixmap)."""
    ov = _make_overlay(qtbot)
    _populate_preview_label(ov, _item(_split_png(tmp_path)))
    QApplication.processEvents()
    fit = _shown(ov)
    assert label_wheel(ov, 480, 0.5, 0.5) is True
    zoomed = _shown(ov)
    assert zoomed != fit
    # Same size, same zoom → cached (no repaint crash, pixmap stable).
    _rescale_preview_to_host(ov)
    QApplication.processEvents()
    assert _shown(ov) == zoomed
    ov.hide()
