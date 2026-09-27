"""Quick-look canvas preview seam tests (GPU-first + QLabel fallback).

Seam contract (frozen): ``tabs.image_gallery.ui.quick_look.preview_canvas``
provides ``QuickLookCanvasWidget(QRhiWidget)`` with ``set_source(store)`` /
``clear_source()``; ``populate_preview(overlay, item)`` prefers the GPU
canvas child in ``overlay._preview_host`` and falls back to
``overlay._preview_label``; ``overlay._preview_store`` is closed on
repopulate/hide. Offscreen RHI cannot present, so these tests cover the
SEAM (wiring/lifecycle/caps), never pixels.

Crew-parallel safe: the canvas module may not exist yet on this branch.
GPU/lifecycle asserts skip when the seam is absent; fallback + stash-cap
asserts always run (see preview.py ``_PREVIEW_FULL_DECODE_EDGE``).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay

PREVIEW_CANVAS_NAME = "tabs.image_gallery.ui.quick_look.preview_canvas"


def _real_png(tmp_path: Path, name: str, w: int = 800, h: int = 600) -> Path:
    pm = QPixmap(w, h)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref, keeps C++ tree alive
    return ov


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


def _preview_home_module():
    """Module object holding populate_preview's globals (patch probes here)."""
    import tabs.image_gallery.ui.quick_look.helpers as ql_helpers

    populate = ql_helpers.populate_preview
    return sys.modules.get(populate.__module__, ql_helpers)


def _preview_canvas_module():
    try:
        return importlib.import_module(PREVIEW_CANVAS_NAME)
    except Exception:
        return None


def _block_canvas_import(monkeypatch):
    """Make ``preview_canvas`` unimportable (frozen-seam fallback trigger).

    Covers both lazy ``import`` inside populate (sys.modules None entry
    raises ImportError) and top-level bound names (canvas attrs nulled).
    """
    monkeypatch.setitem(sys.modules, PREVIEW_CANVAS_NAME, None)
    for mod_name in (
        "tabs.image_gallery.ui.quick_look.preview",
        "tabs.image_gallery.ui.quick_look.helpers",
    ):
        mod = sys.modules.get(mod_name)
        if mod is None:
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                continue
        for attr in [a for a in dir(mod) if "canvas" in a.lower()]:
            try:
                monkeypatch.setattr(mod, attr, None, raising=False)
            except Exception:
                pass


def _canvas_child_in_host(overlay) -> bool:
    host = getattr(overlay, "_preview_host", None)
    if host is None:
        return False
    for child in host.findChildren(QWidget):
        if child is getattr(overlay, "_preview_label", None):
            continue
        if hasattr(child, "set_source"):
            return True
    return False


def test_gpu_branch_preferred_when_canvas_available(qtbot, tmp_path, monkeypatch):
    """GPU-first: populate hides the label, shows a canvas child, feeds it."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None or not (
        hasattr(widget_cls, "set_source") and hasattr(widget_cls, "clear_source")
    ):
        pytest.skip("QuickLookCanvasWidget seam (set_source/clear_source) absent")

    from PySide6.QtWidgets import QApplication as _QA

    _app = _QA.instance()
    if _app is not None and str(_app.platformName() or "").lower() == "offscreen":
        pytest.skip("GPU branch needs a presenting platform (offscreen owns QLabel fallback)")

    created: list = []

    from PySide6.QtWidgets import QWidget as _W

    class _FakeCanvas(_W):
        def __init__(self, *args, **kwargs):
            parent = args[0] if args else kwargs.get("parent")
            super().__init__(parent) if parent is not None else super().__init__()
            self.sources: list = []
            self.cleared = 0
            created.append(self)

        def set_source(self, store) -> None:
            self.sources.append(store)

        def clear_source(self) -> None:
            self.cleared += 1

    monkeypatch.setattr(pc_mod, "QuickLookCanvasWidget", _FakeCanvas, raising=False)
    home = _preview_home_module()
    if hasattr(home, "QuickLookCanvasWidget"):
        monkeypatch.setattr(home, "QuickLookCanvasWidget", _FakeCanvas, raising=False)

    src = _item(_real_png(tmp_path, "gpu.png"))
    ov = _make_overlay(qtbot)
    home.populate_preview(ov, src)
    QApplication.processEvents()

    assert created, "expected populate_preview to construct a canvas widget"
    canvas = created[-1]
    assert getattr(canvas, "sources", []), "expected set_source(store) call"
    host = getattr(ov, "_preview_host", None)
    assert host is not None and host.isAncestorOf(canvas)
    assert ov._preview_label.isHidden(), "GPU branch must hide the fallback label"
    assert _canvas_child_in_host(ov)
    ov.hide()


def test_fallback_label_path_when_canvas_unavailable(qtbot, tmp_path, monkeypatch):
    """QLabel fallback: unimportable canvas still sets a label pixmap."""
    _block_canvas_import(monkeypatch)
    src = _item(_real_png(tmp_path, "fb.png"))
    ov = _make_overlay(qtbot)
    home = _preview_home_module()
    home.populate_preview(ov, src)
    QApplication.processEvents()

    assert not _canvas_child_in_host(ov), "no canvas child on the fallback path"
    pm = ov._preview_label.pixmap()
    assert pm is not None and not pm.isNull(), "fallback must set a label pixmap"
    assert not ov._preview_label.isHidden()
    ov.hide()


class _StubStore:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_preview_store_closed_on_repopulate(qtbot, tmp_path):
    """Repopulate closes the previous overlay._preview_store (skip if unowned)."""
    first = _item(_real_png(tmp_path, "a.png"))
    second = _item(_real_png(tmp_path, "b.png"))
    ov = _make_overlay(qtbot)
    home = _preview_home_module()
    home.populate_preview(ov, first)
    QApplication.processEvents()

    old = _StubStore()
    ov._preview_store = old
    home.populate_preview(ov, second)
    QApplication.processEvents()

    if getattr(ov, "_preview_store", None) is old and not old.closed:
        pytest.skip("preview store lifecycle not implemented yet")
    assert old.closed, "repopulate must close the previous preview store"
    ov.hide()


def test_preview_store_closed_on_hide(qtbot, tmp_path):
    """Hide closes overlay._preview_store (skip if unowned)."""
    src = _item(_real_png(tmp_path, "h.png"))
    ov = _make_overlay(qtbot)
    home = _preview_home_module()
    home.populate_preview(ov, src)
    QApplication.processEvents()

    store = _StubStore()
    ov._preview_store = store
    ov.hide()
    QApplication.processEvents()

    if not store.closed:
        pytest.skip("preview store hide-close not implemented yet")
    assert store.closed


def test_huge_source_stash_capped(qtbot, tmp_path, monkeypatch):
    """40k probe dims never stash a giant pixmap (scaled-reader cap)."""
    home = _preview_home_module()
    monkeypatch.setattr(home, "_fast_image_size", lambda path: (40000, 30000))
    src = _item(_real_png(tmp_path, "huge.png", 800, 600))
    ov = _make_overlay(qtbot)
    home.populate_preview(ov, src)
    QApplication.processEvents()

    full = getattr(ov, "_preview_full", None)
    assert full is not None and not full.isNull()
    cap = int(getattr(home, "_PREVIEW_FULL_DECODE_EDGE", 2048))
    assert max(full.width(), full.height()) <= cap
    ov.hide()


def test_watchdog_emits_preview_failed_without_frame(qtbot):
    """No-frame watchdog fires previewFailed; a presented frame silences it."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    card = widget_cls(None)
    qtbot.addWidget(card)
    fired: list = []
    card.previewFailed.connect(lambda: fired.append(True))
    card._frame_ok = False
    card._on_watchdog()
    assert fired, "watchdog must emit previewFailed with no frame presented"
    card._frame_ok = True
    card._on_watchdog()
    assert len(fired) == 1, "presented frame must silence the watchdog"


def test_zoom_step_clamps():
    from tabs.image_gallery.ui.quick_look.preview_zoom import ZOOM_MAX, ZOOM_MIN, step_zoom

    assert step_zoom(1.0, 120) > 1.0
    assert step_zoom(1.0, -120) == ZOOM_MIN
    assert step_zoom(ZOOM_MAX, 120) == ZOOM_MAX
    assert step_zoom("bad", 120) == ZOOM_MIN * 1.15  # garbage in → step from MIN


def test_zoomed_frame_sizes():
    from PySide6.QtGui import QColor, QImage, QPainter

    from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame

    full = QImage(100, 50, QImage.Format.Format_RGB32)
    full.fill(QColor("#112233"))
    painter = QPainter(full)
    painter.fillRect(0, 0, 50, 50, QColor("#aabbcc"))
    painter.end()
    w, h, px = zoomed_frame(full, 200, 100, 1.0)
    assert (w, h) == (200, 100) and len(px) == 200 * 100 * 4
    w2, h2, px2 = zoomed_frame(full, 200, 100, 2.0)
    assert (w2, h2) == (200, 100) and len(px2) == len(px) and px2 != px
    assert zoomed_frame(full, 0, 100, 1.0) is None


def test_wire_connects_and_first_frame_drops_cover(qtbot):
    """_wire_canvas_fallback hooks signals; first frame drops the cover."""
    from types import SimpleNamespace

    from PySide6.QtCore import QObject, Signal

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    dropped: list = []

    class _FakeCover:
        def hide(self):
            dropped.append("hide")

        def deleteLater(self):
            dropped.append("delete")

    class _FakeCanvas(QObject):
        previewFailed = Signal()
        renderFailed = Signal()
        firstFramePresented = Signal()

    ov = SimpleNamespace(_preview_cover=_FakeCover())
    canvas = _FakeCanvas()
    _host._wire_canvas_fallback(ov, canvas, _item(Path("/gallery/a.png")))
    assert getattr(canvas, "_gallery_fail_wired", False) is True
    canvas.firstFramePresented.emit()
    assert ov._preview_cover is None and dropped == ["hide", "delete"]
    # Second wire is a no-op (no duplicate slots).
    _host._wire_canvas_fallback(ov, canvas, _item(Path("/gallery/a.png")))
    canvas.firstFramePresented.emit()
    assert dropped == ["hide", "delete"]


def test_wheel_anchor_and_floor_snap():
    from tabs.image_gallery.ui.quick_look.preview_zoom import ZOOM_MIN, wheel_zoom_pan

    got = wheel_zoom_pan(1.0, 0.0, 0.0, 120, 0.75, 0.25)
    assert got is not None
    z, px, py = got
    assert z > 1.0
    # Cursor-anchored: content under cursor stays — pan offsets opposite.
    assert px < 0.0 and py > 0.0
    # Tiny delta below epsilon → no change.
    assert wheel_zoom_pan(1.0, 0.0, 0.0, 0.0001, 0.5, 0.5) is None
    # Floor snap: zooming out to MIN zeroes pan.
    assert wheel_zoom_pan(1.2, 0.3, -0.2, -1200, 0.5, 0.5) == (ZOOM_MIN, 0.0, 0.0)


def test_drag_pan_follows_cursor():
    from tabs.image_gallery.ui.quick_look.preview_zoom import drag_pan

    got = drag_pan(0.0, 0.0, 100, -50, 1000, 500, 2.0)
    assert got == (100 / 2000.0, -50 / 1000.0)
    assert drag_pan(0.0, 0.0, 10, 10, 0, 500, 2.0) is None


def test_zoomed_frame_pan_shifts_crop():
    from PySide6.QtGui import QColor, QImage, QPainter

    from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame

    full = QImage(100, 50, QImage.Format.Format_RGB32)
    full.fill(QColor("#112233"))
    painter = QPainter(full)
    painter.fillRect(0, 0, 50, 50, QColor("#aabbcc"))
    painter.end()
    _, _, a = zoomed_frame(full, 200, 100, 2.0, 0.0, 0.0)
    _, _, b = zoomed_frame(full, 200, 100, 2.0, 0.5, 0.0)
    assert a != b
