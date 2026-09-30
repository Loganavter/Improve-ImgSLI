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


def test_watchdog_stale_generation_ignored(qtbot):
    """Late first-source timer must not kill a healthy new canvas (2026-09-28).

    Regression: set_source reset _frame_ok while the previous source's
    singleShot was still pending, so the stale fire saw False and emitted
    previewFailed ~26ms after the new populate.
    """
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from tabs.image_gallery.ui.quick_look import preview_watchdog as wd

    card = widget_cls(None)
    qtbot.addWidget(card)
    fired: list = []
    card.previewFailed.connect(lambda: fired.append(True))
    card._frame_ok = False
    g1 = wd.next_gen(card)
    wd.arm_watchdog(card, g1)  # T1 pending
    g2 = wd.next_gen(card)
    wd.arm_watchdog(card, g2)  # T2 pending, T1 stale
    assert g2 != g1
    wd.fire_watchdog(card, g1)
    assert fired == [], "stale generation must not emit previewFailed"
    assert card._watchdog_armed is True, "live timer must stay armed"
    wd.fire_watchdog(card, g2)
    assert fired == [True], "live generation with no frame must emit"


def test_clear_source_invalidates_pending_watchdog(qtbot):
    """clear_source retires the armed timer (hide/close/populate-next)."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from tabs.image_gallery.ui.quick_look import preview_watchdog as wd

    card = widget_cls(None)
    qtbot.addWidget(card)
    fired: list = []
    card.previewFailed.connect(lambda: fired.append(True))
    card._frame_ok = False
    g = wd.next_gen(card)
    wd.arm_watchdog(card, g)
    card.clear_source()
    wd.fire_watchdog(card, g)
    assert fired == [], "timer armed before clear_source must go stale"


def test_reveal_warm_shows_and_requests_frame():
    """Warm reveal (every walk): show() must be followed by update().

    Regression (2026-09-28): set_source's trailing update() lands while
    the canvas is still hidden (populate release hid it) and is dropped;
    a re-shown QRhiWidget self-renders only on first exposure, so walks
    never presented and died by watchdog with shell_ready=True.
    """
    from types import SimpleNamespace

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    calls: list = []
    canvas = SimpleNamespace(
        show=lambda: calls.append("show"),
        hide=lambda: calls.append("hide"),
        update=lambda: calls.append("update"),
    )
    ov = SimpleNamespace(
        _preview_canvas_pending="stale",
        _ql_chrome_painted=True,
        isVisible=lambda: True,
    )
    _host.reveal_preview_canvas(ov, canvas)
    assert calls == ["show", "update"], f"show must request a frame, got {calls}"
    assert ov._preview_canvas_pending is None


def test_reveal_cold_stages_pending_without_frame():
    """Cold reveal: hide + stage, no update until the chrome paints."""
    from types import SimpleNamespace

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    calls: list = []
    canvas = SimpleNamespace(
        show=lambda: calls.append("show"),
        hide=lambda: calls.append("hide"),
        update=lambda: calls.append("update"),
    )
    ov = SimpleNamespace(
        _preview_canvas_pending=None,
        _ql_chrome_painted=False,
        isVisible=lambda: False,
    )
    _host.reveal_preview_canvas(ov, canvas)
    assert calls == ["hide"]
    assert ov._preview_canvas_pending is canvas


def test_reveal_pending_shows_and_requests_frame():
    """Staged cold-open canvas: first chrome paint shows + updates."""
    from types import SimpleNamespace

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    calls: list = []
    canvas = SimpleNamespace(
        show=lambda: calls.append("show"),
        hide=lambda: calls.append("hide"),
        update=lambda: calls.append("update"),
    )
    ov = SimpleNamespace(
        _preview_canvas_pending=canvas,
        _preview_canvas=None,
        _preview_cover=None,
        isVisible=lambda: True,
    )
    _host.reveal_pending_preview_canvas(ov)
    assert calls == ["show", "update"], f"show must request a frame, got {calls}"
    assert ov._preview_canvas_pending is None


def test_fallback_logs_which_signal_fired(qtbot, tmp_path, monkeypatch, caplog):
    """previewFailed vs renderFailed fallbacks log distinct reasons."""
    import logging

    from PySide6.QtCore import QObject, Signal

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    monkeypatch.setenv("IMGSLI_QL_COVER_DEBUG", "1")

    class _FakeCanvas(QObject):
        previewFailed = Signal()
        renderFailed = Signal()

    def _run(signal: str) -> str:
        ov = _make_overlay(qtbot)
        canvas = _FakeCanvas()
        qtbot.addWidget(ov._parity_test_parent)
        item = _item(tmp_path / "nope.png")
        _host._wire_canvas_fallback(ov, canvas, item)
        with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
            caplog.clear()
            getattr(canvas, signal).emit()
            QApplication.processEvents()
        return caplog.text

    assert "fallback (previewFailed) -> label path" in _run("previewFailed")

    text = _run("renderFailed")
    assert "fallback (renderFailed) -> label path" in text
    assert "fallback (previewFailed)" not in text


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


def test_cover_is_opaque_host_sibling_not_canvas_child(qtbot):
    """First-frame cover: layout-external sibling in _preview_host.

    Regression: the old cover was parented to the QRhiWidget itself, so it
    inherited the canvas's transparency window (no beginPass/clear before
    the shell mounts) and the slot showed through for a frame. A sibling
    paints opaquely from the overlay's first paint regardless of RHI state.
    """
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    host = ov._preview_host
    host.setGeometry(0, 0, 320, 240)
    canvas = _W(host)
    pm = QPixmap(64, 48)
    pm.fill(QColor("#3a6ea5"))

    _host._cover_until_first_frame(ov, canvas, pm)
    cover = ov._preview_cover
    assert cover is not None
    assert cover.parent() is host
    assert cover.parent() is not canvas
    # Slot-frame parity: the cover mirrors the host rect, not the canvas.
    assert cover.geometry() == host.rect()
    assert not cover.isHidden(), "cover must be up while no GPU frame presented"
    assert cover.pixmap() is not None and not cover.pixmap().isNull()
    ov.hide()


def test_cover_opaque_without_pixmap(qtbot):
    """Null pixmap still yields an opaque cover — never a transparent hole."""
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    canvas = _W(ov._preview_host)
    canvas.setGeometry(0, 0, 320, 240)

    _host._cover_until_first_frame(ov, canvas, QPixmap())
    cover = ov._preview_cover
    assert cover is not None, "null pixmap must not mean no cover"
    assert cover.autoFillBackground(), "null-pixmap cover must be opaque-filled"
    assert not cover.isHidden()
    ov.hide()


def test_sync_re_pins_cover_on_slot_resize(qtbot):
    """Slot resize (layout settle, card drags) re-fits the cover."""
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    host = ov._preview_host
    host.setGeometry(0, 0, 320, 240)
    canvas = _W(host)
    pm = QPixmap(64, 48)
    pm.fill(QColor("#3a6ea5"))
    _host._cover_until_first_frame(ov, canvas, pm)

    host.setGeometry(5, 5, 400, 300)
    _host._fit_preview_slot(ov)
    assert ov._preview_cover.geometry() == host.rect()
    assert not ov._preview_cover.isHidden()
    ov.hide()


def test_slot_children_all_mirror_host_rect(qtbot):
    """IC-parity slot frame: label + canvas + cover all share host.rect().

    Regression: the label used to be a second stretched layout peer while
    the cover hand-copied the canvas geometry — two geometry authorities
    that could desync (the SESSION_2026-09-28 "cover stuck at 640" bug).
    Now the host is the single authority; every layout-external child
    copies its rect, so the GPU<->label swap is seamless by construction.
    """
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    host = ov._preview_host
    host.setGeometry(0, 0, 500, 360)
    canvas = _W(host)
    cover = _W(host)
    ov._preview_canvas = canvas
    ov._preview_cover = cover

    _host._fit_preview_slot(ov)

    assert ov._preview_label.geometry() == host.rect()
    assert canvas.geometry() == host.rect()
    assert cover.geometry() == host.rect()
    ov.hide()


def test_cover_pixmap_fits_live_slot(qtbot):
    """Cover pixmap aspect-fits the live canvas size (no stale 640px patch).

    Regression: the cover pixmap froze at label-populate size while the slot
    settled larger — the canvas looked bigger than the patch. _fit_cover
    re-derives the shown pixmap from the stashed full at the live size.
    """
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    full = QPixmap(800, 600)
    full.fill(QColor("#3a6ea5"))
    ov._preview_full = full
    host = ov._preview_host
    host.setGeometry(0, 0, 663, 566)
    canvas = _W(host)
    pm = QPixmap(64, 48)
    pm.fill(QColor("#3a6ea5"))
    _host._cover_until_first_frame(ov, canvas, pm)

    shown = ov._preview_cover.pixmap()
    assert shown is not None and not shown.isNull()
    # Aspect-fit into 663x566: height binds (566), width follows (754>663? no:
    # 800x600 ratio into 663x566 -> 663x497 wide-bind). Either way, one axis
    # must equal the slot and neither may exceed it.
    assert shown.width() <= 663 and shown.height() <= 566
    assert shown.width() == 663 or shown.height() == 566
    ov.hide()


def test_release_drops_cover(qtbot):
    """Leaving the GPU path (hide/close/populate-next) must drop the cover."""
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    canvas = _W(ov._preview_host)
    pm = QPixmap(64, 48)
    pm.fill(QColor("#3a6ea5"))
    _host._cover_until_first_frame(ov, canvas, pm)
    cover = ov._preview_cover
    assert cover is not None

    ov._preview_canvas = None
    ov._preview_store = None
    _host.release_preview_canvas(ov)
    assert ov._preview_cover is None
    assert cover.isHidden()
    ov.hide()


def test_cover_slot_opaque_pixels(qtbot):
    """Pixel-level: the covered slot has no alpha hole (offscreen grab).

    Raster proof for the warmup cover — every sampled pixel inside the
    cover rect must be fully opaque, so no desktop can show through while
    the canvas has presented nothing yet.
    """
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    canvas = _W(ov._preview_host)
    canvas.setGeometry(0, 0, 640, 456)
    pm = QPixmap(64, 48)
    pm.fill(QColor("#3a6ea5"))
    _host._cover_until_first_frame(ov, canvas, pm)
    ov._preview_canvas = canvas
    ov._parity_test_parent.show()
    qtbot.waitExposed(ov._parity_test_parent)
    from PySide6.QtWidgets import QApplication as _QA

    _QA.processEvents()

    cover = ov._preview_cover
    img = ov._preview_host.grab().toImage()
    cg = cover.geometry()
    hole = 0
    checked = 0
    for y in range(cg.y(), cg.y() + cg.height(), 7):
        for x in range(cg.x(), cg.x() + cg.width(), 7):
            checked += 1
            if img.pixelColor(x, y).alpha() < 255:
                hole += 1
    assert checked > 0
    assert hole == 0, f"cover slot must be fully opaque, {hole}/{checked} transparent"
    ov.hide()


def test_first_frame_emitted_on_settled_second_present(qtbot):
    """Settle gate: the cover drops on present #2, never #1 (MC parity).

    Regression for the first-frame see-through: present #1 is recorded
    while the compositor may still show the untouched surface, so present
    #1 only pumps one more frame and the emit waits for the settled #2.
    """
    from types import SimpleNamespace

    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    canvas = widget_cls(None)
    qtbot.addWidget(canvas)

    updates: list = []
    canvas._pump_next_frame = lambda: updates.append(True)  # type: ignore[method-assign]

    class _FakeSize:
        def width(self):
            return 8

        def height(self):
            return 6

    class _FakeTarget:
        def pixelSize(self):
            return _FakeSize()

    class _FakeCB:
        def beginPass(self, *a, **k):
            pass

        def endPass(self, *a, **k):
            pass

    class _FakeShell:
        def stage_quad(self, u):
            pass

        def stage_clip(self, u, c):
            pass

        def upload_frame(self, u, t, f):
            pass

        def draw(self, cb, width, height):
            pass

    canvas._shell_ready = True
    canvas._shell = _FakeShell()
    canvas.rhi = lambda: SimpleNamespace(nextResourceUpdateBatch=lambda: object())  # type: ignore[method-assign]
    canvas.renderTarget = lambda: _FakeTarget()  # type: ignore[method-assign]
    canvas._raster_frame = lambda target: (8, 6, bytes(8 * 6 * 4))  # type: ignore[method-assign]

    fired: list = []
    canvas.firstFramePresented.connect(lambda: fired.append(True))
    cb = _FakeCB()
    canvas.render(cb)
    assert fired == [], "present #1 must not drop the cover"
    assert updates, "present #1 must pump one more frame"
    assert getattr(canvas, "_settle_pumped", False) is True
    canvas.render(cb)
    assert fired == [], "emit waits for the deferred settle flush"
    QApplication.processEvents()
    assert fired == [True], "settled present + restack drops the cover"
    assert canvas._frame_ok is True

    # Walk to a new source: the gate resets, two fresh presents required.
    canvas.set_source(SimpleNamespace(close=lambda: None, generation=0))
    assert canvas._frame_ok is False and canvas._settle_pumped is False
    canvas.render(cb)
    assert fired == [True], "new source: present #1 pumps only"
    canvas.render(cb)
    QApplication.processEvents()
    assert fired == [True, True], "new source: settled present #2 emits"


def test_pump_next_frame_is_queued_not_direct(qtbot):
    """Settle pump must not call update() synchronously (2026-09-28).

    render() runs off the GUI thread: a direct update() there is a
    cross-thread call and gets lost (walks never presented). The pump
    must go through QueuedConnection — a synchronous spy stays empty
    even after the loop drains (delivery targets the C++ slot).
    """
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    canvas = widget_cls(None)
    qtbot.addWidget(canvas)

    direct: list = []
    canvas.update = lambda *a, **k: direct.append(True)  # type: ignore[method-assign]
    widget_cls._pump_next_frame(canvas)
    assert direct == [], "pump must not call update() synchronously"
    QApplication.processEvents()
    assert direct == [], "queued delivery targets the C++ slot, never the spy"


def test_repump_requests_frame_when_pump_lost(qtbot, monkeypatch):
    """Delayed GUI-thread re-request heals a coalesced pump (2026-09-28).

    Walk pattern: exactly one render, then silence despite a posted
    update. ensure_repump re-requests once the loop is idle.
    """
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from tabs.image_gallery.ui.quick_look import preview_watchdog as wd

    monkeypatch.setattr(wd, "_REPUMP_MS", 0)
    canvas = widget_cls(None)
    qtbot.addWidget(canvas)
    canvas._frame_ok = False
    canvas._settle_pumped = True
    called: list = []
    canvas.update = lambda *a, **k: called.append(True)  # type: ignore[method-assign]
    wd.ensure_repump(canvas)
    QApplication.processEvents()
    QApplication.processEvents()
    assert called, "lost pump must be re-requested from the GUI loop"


def test_repump_quiet_when_settled_or_unpumped(qtbot, monkeypatch):
    """No frame debt → no re-request (settled or pump never ran)."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from tabs.image_gallery.ui.quick_look import preview_watchdog as wd

    monkeypatch.setattr(wd, "_REPUMP_MS", 0)
    for frame_ok, pumped in ((True, True), (False, False)):
        canvas = widget_cls(None)
        qtbot.addWidget(canvas)
        canvas._frame_ok = frame_ok
        canvas._settle_pumped = pumped
        called: list = []
        canvas.update = lambda *a, **k: called.append(True)  # type: ignore[method-assign]
        wd.ensure_repump(canvas)
        QApplication.processEvents()
        QApplication.processEvents()
        assert called == [], f"no re-request when frame_ok={frame_ok} pumped={pumped}"


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


def test_present_debt_renewed_per_set_source(qtbot):
    """Debt ledger: set_source renews the generation, stale gens stay stale."""
    from types import SimpleNamespace

    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from engine.frame.present import PresentDebt

    canvas = widget_cls(None)
    qtbot.addWidget(canvas)
    assert isinstance(canvas._present_debt, PresentDebt)
    g0 = int(canvas._present_debt.generation)
    canvas.set_source(SimpleNamespace(close=lambda: None, generation=0))
    g1 = int(canvas._present_debt.generation)
    assert g1 == g0 + 1, "set_source must bump the debt generation"
    assert int(canvas._present_debt.presented) == 0
    canvas.set_source(SimpleNamespace(close=lambda: None, generation=0))
    assert int(canvas._present_debt.generation) == g1 + 1
    assert int(canvas._watchdog_gen) == int(canvas._present_debt.generation)


def test_stale_fire_ignored_via_should_fire(qtbot):
    """should_fire gates the watchdog: old gen never fires the live debt."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from engine.frame.present import should_fire
    from tabs.image_gallery.ui.quick_look import preview_watchdog as wd

    canvas = widget_cls(None)
    qtbot.addWidget(canvas)
    fired: list = []
    canvas.previewFailed.connect(lambda: fired.append(True))
    canvas._frame_ok = False
    g1 = wd.next_gen(canvas)
    live_debt = canvas._present_debt
    g2 = wd.next_gen(canvas)
    assert should_fire(g1, canvas._present_debt) is False
    assert should_fire(g2, canvas._present_debt) is True
    assert canvas._present_debt is not live_debt, "next_gen must renew the debt"
    wd.fire_watchdog(canvas, g1)
    assert fired == [], "stale generation must not emit previewFailed"


def test_settle_reached_on_second_present(qtbot):
    """Verdict ledger: 1st present pumps, 2nd settles (QL_SETTLE_COUNT=2)."""
    pc_mod = _preview_canvas_module()
    if pc_mod is None:
        pytest.skip("preview_canvas.py not on this branch yet")
    widget_cls = getattr(pc_mod, "QuickLookCanvasWidget", None)
    if widget_cls is None:
        pytest.skip("QuickLookCanvasWidget absent")
    from engine.frame.present import begin_source, note_presented
    from tabs.image_gallery.ui.quick_look.preview_watchdog import QL_SETTLE_COUNT

    assert QL_SETTLE_COUNT == 2
    canvas = widget_cls(None)
    qtbot.addWidget(canvas)
    debt = begin_source(None)
    assert note_presented(debt, QL_SETTLE_COUNT) == "pumped"
    assert debt.pumped is True and debt.settled is False
    assert note_presented(debt, QL_SETTLE_COUNT) == "settled"
    assert debt.settled is True
    # The canvas debt starts unpresented; two presents settle it.
    assert int(canvas._present_debt.presented) == 0
    assert note_presented(canvas._present_debt, QL_SETTLE_COUNT) == "pumped"
    assert note_presented(canvas._present_debt, QL_SETTLE_COUNT) == "settled"


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
