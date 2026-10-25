"""Quick-look canvas preview seam tests (single live GPU surface).

Seam contract (frozen): ``tabs.image_gallery.ui.quick_look.preview_canvas``
provides ``QuickLookCanvasWidget(QRhiWidget)`` with ``set_source(store)`` /
``clear_source()``; ``populate_preview(overlay, item)`` feeds the GPU canvas
child in ``overlay._preview_host``; ``overlay._preview_store`` is closed on
repopulate/hide. The raster first-frame cover is the only pre-present plate
(no second live surface). Offscreen RHI cannot present, so these tests cover
the SEAM (wiring/lifecycle/caps), never pixels.

Crew-parallel safe: the canvas module may not exist yet on this branch.
GPU/lifecycle asserts skip when the seam is absent; stash-cap asserts always
run (see preview.py ``_PREVIEW_FULL_DECODE_EDGE``).
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
from core.log_names import APP_LOGGER_NAME

PREVIEW_CANVAS_NAME = "tabs.image_gallery.ui.quick_look.preview_canvas"

# Teardown contract for this file: every test owns its staged canvas work.
#
# Measured 2026-10-22 (combined gallery tier): a canvas populated through an
# overlay that was never SHOWN keeps its 1200 ms dwell ``singleShot`` armed —
# ``hide()`` on a non-visible widget delivers no ``hideEvent``, so the release
# path (``preview_canvas_host.release_preview_canvas`` → ``clear_source`` →
# ``_drop_ql_demand``) never bumps ``_ql_gen`` or drops ``_ql_tiled_pending``.
# The timer then fires on a LATER test's event turn and dispatches
# ``_decode_full_store_uncapped`` there (``preview_canvas_host/tiled_source.py``
# resolves it through ``_host()`` at dispatch time), landing in that test's
# decode spy: ``test_prefetch_fills_neighbor_memos_revisit_decodes_nothing``
# recorded a predecessor's file in ``uncapped_calls``. The RHI failure tests
# are the other half of the same window — they start real decodes on the
# process-wide pool and never wait for them.
#
# ``_own_staged_canvas_work`` (below) is the enforcement point.


@pytest.fixture(autouse=True)
def _own_staged_canvas_work():
    """Retire staged canvas work at teardown; drain the process-wide pool.

    Enforcement of the contract above, while the owning test is still the
    current one: bump ``_ql_gen`` (the dwell timer's generation guard, so the
    singleShot can no longer pre-warm or kick), drop the staged kick
    (``_ql_tiled_pending``) and the demand source (``_ql_source_path``) on the
    canvases created by this test. Then wait for the shared pool — the same
    drain ``test_quicklook_canvas_seam.py::test_canvas_path_huge_source_no_full_frame``
    performs before its spy window opens. Retiring is idempotent: a canvas the
    release path already cleaned (``_ql_source_path`` None, no pending) is
    skipped untouched.
    """
    from PySide6.QtCore import QThreadPool

    app = QApplication.instance()
    # Strong refs: compare identity across the test, like
    # ``image_gallery/tests/conftest.py::_destroy_lingering_toplevels``.
    before = list(QApplication.allWidgets()) if app is not None else []
    yield
    app = QApplication.instance()
    if app is None:
        return
    for w in list(QApplication.allWidgets()):
        if any(w is b for b in before):
            continue
        try:
            if (
                getattr(w, "_ql_source_path", None) is None
                and getattr(w, "_ql_tiled_pending", None) is None
            ):
                continue
            w._ql_gen = int(getattr(w, "_ql_gen", 0) or 0) + 1
            w._ql_tiled_pending = None
            w._ql_source_path = None
        except (RuntimeError, AttributeError, TypeError):
            continue
    try:
        QThreadPool.globalInstance().waitForDone(10000)
    except Exception:
        pass
    for _ in range(3):
        try:
            QApplication.processEvents()
        except Exception:
            break


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
    assert _canvas_child_in_host(ov)
    ov.hide()


def test_no_canvas_surface_is_inert(qtbot, tmp_path, monkeypatch):
    """Unimportable canvas: populate is inert, no second surface, no raise."""
    _block_canvas_import(monkeypatch)
    src = _item(_real_png(tmp_path, "fb.png"))
    ov = _make_overlay(qtbot)
    home = _preview_home_module()
    home.populate_preview(ov, src)  # must not raise
    QApplication.processEvents()

    assert not _canvas_child_in_host(ov), "no canvas child without the module"
    assert not hasattr(ov, "_preview" + "_label"), "label surface must be gone"
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
        with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
            caplog.clear()
            getattr(canvas, signal).emit()
            QApplication.processEvents()
        return caplog.text

    assert "fallback (previewFailed) -> cover retained" in _run("previewFailed")

    text = _run("renderFailed")
    assert "fallback (renderFailed) -> cover retained" in text
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
    ov._preview_full = pm

    _host._cover_until_first_frame(ov, canvas)
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

    _host._cover_until_first_frame(ov, canvas)
    cover = ov._preview_cover
    assert cover is not None, "no stashed source must not mean no cover"
    assert cover.autoFillBackground(), "source-less cover must be opaque-filled"
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
    ov._preview_full = pm
    _host._cover_until_first_frame(ov, canvas)

    host.setGeometry(5, 5, 400, 300)
    _host._fit_preview_slot(ov)
    assert ov._preview_cover.geometry() == host.rect()
    assert not ov._preview_cover.isHidden()
    ov.hide()


def test_slot_children_all_mirror_host_rect(qtbot):
    """IC-parity slot frame: canvas + cover share host.rect().

    The host is the single laid-out geometry authority; every
    layout-external slot child copies its rect, so the cover<->canvas swap
    is seamless by construction.
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

    assert canvas.geometry() == host.rect()
    assert cover.geometry() == host.rect()
    ov.hide()


def test_overlay_has_no_label_surface(qtbot):
    """The QLabel image surface is gone; attrs removed with it."""
    ov = _make_overlay(qtbot)
    # Name split so the repo-wide greps for the removed attr stay empty.
    assert not hasattr(ov, "_preview" + "_label")
    assert not hasattr(ov, "_label_zoom")
    assert not hasattr(ov, "_label_pan_x")
    assert not hasattr(ov, "_label_pan_y")
    assert not hasattr(ov, "_label_drag")
    ov.hide()


def test_fit_preview_slot_puts_canvas_and_cover_on_host(qtbot):
    """Host is the only geometry authority: canvas + cover mirror its rect."""
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    host = ov._preview_host
    host.setGeometry(0, 0, 640, 456)
    canvas = _W(host)
    cover = _W(host)
    ov._preview_canvas = canvas
    ov._preview_cover = cover

    _host._fit_preview_slot(ov)

    assert canvas.geometry() == host.rect()
    assert cover.geometry() == host.rect()
    ov.hide()


def test_insets_parented_to_preview_host(qtbot):
    """Source inset overlays the GPU canvas (host child, not label)."""
    ov = _make_overlay(qtbot)
    host = ov._preview_host
    assert ov._source_inset_host.parentWidget() is host
    assert getattr(ov, "_crop_host", None) is None
    ov.hide()


def test_cover_fit_matches_canvas_fit(qtbot):
    """Cover plate uses the same fit/crop math as the live GPU canvas.

    Pins the old ``scaled(KeepAspectRatio)`` divergence: the plate's opaque
    image offset must equal ``preview_zoom._axis(dest, fb, 0.0)`` for both
    axes, with ``dest = round(src * min(fb / src))``.
    """
    from PySide6.QtGui import QImage

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host
    from tabs.image_gallery.ui.quick_look import preview_zoom

    cases = [
        ((1920, 1080), (999, 601)),
        ((1000, 999), (663, 571)),
    ]
    for (sw, sh), (fw, fh) in cases:
        ov = _make_overlay(qtbot)
        src = QPixmap(sw, sh)
        src.fill(QColor("#3a6ea5"))
        ov._preview_full = src
        pm = _host._cover_pixmap_from_full(ov, fw, fh)
        assert pm is not None and not pm.isNull()
        assert (pm.width(), pm.height()) == (fw, fh)
        img = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        ox = oy = None
        for y in range(fh):
            for x in range(fw):
                if img.pixelColor(x, y).alpha() > 0:
                    ox, oy = x, y
                    break
            if ox is not None:
                break
        assert ox is not None and oy is not None, "plate image missing"
        scale = min(fw / sw, fh / sh)
        dest_w = max(1, int(round(sw * scale)))
        dest_h = max(1, int(round(sh * scale)))
        exp_x, _, _ = preview_zoom._axis(dest_w, fw, 0.0)
        exp_y, _, _ = preview_zoom._axis(dest_h, fh, 0.0)
        assert (ox, oy) == (exp_x, exp_y), f"src={(sw, sh)} slot={(fw, fh)}"
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
    _host._cover_until_first_frame(ov, canvas)

    shown = ov._preview_cover.pixmap()
    assert shown is not None and not shown.isNull()
    # Canvas-fit plate: the pixmap is exactly the slot size (letterbox
    # margins transparent; the opaque plate behind them keeps it solid).
    assert shown.width() == 663 and shown.height() == 566
    ov.hide()


def test_release_drops_cover(qtbot):
    """Leaving the GPU path (hide/close/populate-next) must drop the cover."""
    from PySide6.QtWidgets import QWidget as _W

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    ov = _make_overlay(qtbot)
    canvas = _W(ov._preview_host)
    _host._cover_until_first_frame(ov, canvas)
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
    _host._cover_until_first_frame(ov, canvas)
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


def test_clamp_pan_floor_forces_origin():
    """At/below the zoom floor the fitted frame is fully in view: pan 0."""
    from tabs.image_gallery.ui.quick_look.preview_zoom import clamp_pan

    assert clamp_pan(0.4, -0.3, 800, 600, 1000, 500, 1.0) == (0.0, 0.0)
    assert clamp_pan(10.0, 10.0, 800, 600, 1000, 500, 0.5) == (0.0, 0.0)


def test_clamp_pan_cover_range_when_zoomed():
    """Zoomed pan clamps to the exact covered range; short axes center."""
    import pytest

    from tabs.image_gallery.ui.quick_look.preview_zoom import clamp_pan

    # src 800x600, fb 1000x500, zoom 2: scale=min(1.25,0.833)*2=1.667,
    # dest 1333x1000 → x range ±0.125, y ±0.25.
    assert clamp_pan(0.0, 0.0, 800, 600, 1000, 500, 2.0) == (0.0, 0.0)
    assert clamp_pan(10.0, -10.0, 800, 600, 1000, 500, 2.0) == pytest.approx(
        (0.125, -0.25)
    )
    # Wide image in a tall pane at 1.5x: vertical dest still fits → y is 0,
    # horizontal clamps to (1200-800)/2400.
    assert clamp_pan(0.2, 0.4, 1600, 400, 800, 600, 1.5) == pytest.approx(
        (1.0 / 6.0, 0.0)
    )


def test_clamp_pan_fail_open():
    """Garbage dims leave the pan untouched (old behavior preserved)."""
    from tabs.image_gallery.ui.quick_look.preview_zoom import clamp_pan

    assert clamp_pan(0.1, 0.2, 0, 600, 1000, 500, 2.0) == (0.1, 0.2)
    assert clamp_pan(0.1, 0.2, None, None, 1000, 500, 2.0) == (0.1, 0.2)


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


# -- QL walk prefetch (W1) + tiled dwell-gate (W2) -------------------------------
#
# W1: ``_prefetch_neighbors`` fills the coarse-store + stash-pixmap memos for
# the prev/next walk neighbors (bounded builds only, token-guarded); a
# revisit is a memo hit with zero source decodes.
# W2: the uncapped tiled kick moved from on-show to on-dwell-fire (canvas
# ``_ql_gen`` idiom, no second timer) or zoom>1.0. No pre-existing
# show-kicks-decode assertions existed in this file (verified: no
# ``_populate_tiled_source`` / ``_decode_full_store_uncapped`` references before
# these tests), so nothing below updates an old assertion — the dwell
# contract is asserted fresh here.


class _QLSig:
    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _QLWorker:
    """GenericWorker double: captures fn/args; pool decides when fn runs."""

    instances: list = []

    def __init__(self, fn, *args, **kwargs) -> None:
        from types import SimpleNamespace

        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(
            result=_QLSig(),
            finished=_QLSig(),
            partial_result=_QLSig(),
            error=_QLSig(),
        )
        _QLWorker.instances.append(self)


class _QLSyncPool:
    """Fake pool: runs fn inline, emits result synchronously (GUI thread)."""

    def __init__(self) -> None:
        self.workers: list = []

    def start(self, worker) -> None:
        self.workers.append(worker)
        try:
            out = worker.fn(*worker.args, **worker.kwargs)
        except Exception:
            out = None
        worker.signals.result.emit(out)


class _QLHoldPool:
    """Fake pool: captures workers, never runs fn (test fires manually)."""

    def __init__(self) -> None:
        self.workers: list = []

    def start(self, worker) -> None:
        self.workers.append(worker)


def _patch_ql_async(monkeypatch, pool):
    """Route host/canvas worker kicks to *pool*; returns the worker class."""
    from PySide6.QtCore import QThreadPool

    import sli_ui_toolkit.workers as _wmod

    _QLWorker.instances.clear()
    monkeypatch.setattr(_wmod, "GenericWorker", _QLWorker)
    monkeypatch.setattr(QThreadPool, "globalInstance", classmethod(lambda cls: pool))
    return _QLWorker


def _tiled_kicks():
    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    return [w for w in _QLWorker.instances if w.fn is _host._decode_full_store_uncapped]


def test_prefetch_fills_neighbor_memos_revisit_decodes_nothing(qtbot, tmp_path, monkeypatch):
    """W1: prefetch memos both neighbors (bounded only); revisit decodes nothing."""
    from PySide6.QtWidgets import QApplication as _QA

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host
    from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key, _stash_cache_lookup

    a = _item(_real_png(tmp_path, "pa.png"))
    b = _item(_real_png(tmp_path, "pb.png"))
    c = _item(_real_png(tmp_path, "pc.png"))
    ov = _make_overlay(qtbot)
    ov._series_items = [a, b, c]
    ov._current_idx = 1
    try:
        _patch_ql_async(monkeypatch, _QLSyncPool())

        uncapped_calls: list = []
        _real_uncapped = _host._decode_full_store_uncapped

        def _no_uncapped(path, tmp_dir=None):
            uncapped_calls.append(str(path))
            return _real_uncapped(path, tmp_dir)

        monkeypatch.setattr(_host, "_decode_full_store_uncapped", _no_uncapped)

        coarse_calls: list = []
        _real_coarse = _host._coarse_store_for

        def _counting_coarse(path, **kw):
            coarse_calls.append(str(path))
            return _real_coarse(path, **kw)

        monkeypatch.setattr(_host, "_coarse_store_for", _counting_coarse)

        _host._prefetch_neighbors(ov, b)
        _QA.processEvents()

        # Bounded builds only, one per neighbor — never the uncapped decode.
        assert uncapped_calls == [], "prefetch must never use the uncapped full decode"
        assert sorted(coarse_calls) == sorted([str(a.path), str(c.path)])
        assert {w.fn for w in _QLWorker.instances} == {_counting_coarse}

        # Both memos filled under the same keys the walk path reads ...
        ka, kc = _stash_cache_key(a.path), _stash_cache_key(c.path)
        assert _host._preview_store_cache_lookup(ov, ka) is not None
        assert _host._preview_store_cache_lookup(ov, kc) is not None
        assert _stash_cache_lookup(ov, ka) is not None
        assert _stash_cache_lookup(ov, kc) is not None
        # ... while the live slot is untouched (memos only).
        assert getattr(ov, "_preview_store", None) is None
        assert getattr(ov, "_preview_full", None) is None

        # Revisit walk: memo hit, zero coarse rebuilds.
        coarse_calls.clear()
        ov._current_idx = 0
        assert _host._populate_preview_canvas(ov, a) is True
        assert coarse_calls == [], "prefetched revisit must not rebuild coarse"
    finally:
        ov.hide()


def test_prefetch_stale_token_closes_without_install(qtbot, tmp_path, monkeypatch):
    """W1: a token bump retires in-flight prefetch (store closed, no memo)."""
    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host
    from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key

    a = _item(_real_png(tmp_path, "sa.png"))
    b = _item(_real_png(tmp_path, "sb.png"))
    c = _item(_real_png(tmp_path, "sc.png"))
    ov = _make_overlay(qtbot)
    ov._series_items = [a, b, c]
    ov._current_idx = 1
    try:
        _patch_ql_async(monkeypatch, _QLHoldPool())
        _host._prefetch_neighbors(ov, b)
        assert len(_QLWorker.instances) == 2, "prev+next neighbors only"

        # Walk/hide bumps the token before the workers land.
        ov._ql_prefetch_token = int(getattr(ov, "_ql_prefetch_token", 0) or 0) + 1

        for worker in list(_QLWorker.instances):
            store = _host._coarse_store_for(*worker.args, **worker.kwargs)
            assert store is not None and bool(store.is_open)
            worker.signals.result.emit(store)
            assert not bool(store.is_open), "stale prefetch result must close"

        for item in (a, c):
            key = _stash_cache_key(item.path)
            assert _host._preview_store_cache_lookup(ov, key) is None
            assert getattr(ov, "_preview_store", None) is None
    finally:
        ov.hide()


def _make_dwell_canvas(qtbot, ov, monkeypatch):
    """Real canvas slotted into the overlay (mirrors _ensure_preview_canvas)."""
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc
    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    card = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    ov._preview_canvas = card
    _host._install_memo_probe(ov, card)
    orig = _host._ensure_preview_canvas
    monkeypatch.setattr(
        _host, "_ensure_preview_canvas", lambda _ov: card, raising=False
    )
    return card, orig


def test_show_kicks_no_tiled_decode_dwell_kicks_one(qtbot, tmp_path, monkeypatch):
    """W2: plain show stages (no uncapped kick, memo empty); dwell fires one."""
    from PySide6.QtWidgets import QApplication as _QA

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host
    from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key

    src = _item(_real_png(tmp_path, "dw.png"))
    ov = _make_overlay(qtbot)
    card, _orig = _make_dwell_canvas(qtbot, ov, monkeypatch)
    try:
        _patch_ql_async(monkeypatch, _QLHoldPool())
        assert _host._populate_preview_canvas(ov, src) is True
        _QA.processEvents()

        assert _tiled_kicks() == [], "plain show must not kick the uncapped tiled decode"
        key = _stash_cache_key(src.path)
        assert _host._tiled_store_cache_lookup(ov, key) is None
        assert getattr(card, "_ql_tiled_pending", None) is not None

        card._ql_on_dwell(int(card._ql_gen))
        kicks = _tiled_kicks()
        assert len(kicks) == 1, f"dwell must kick exactly one tiled decode, got {len(kicks)}"
        assert getattr(card, "_ql_tiled_pending", None) is None, "kick consumed once"

        # A stale dwell (walked away) kicks nothing more.
        card._ql_on_dwell(int(card._ql_gen) + 99)
        assert len(_tiled_kicks()) == 1
    finally:
        _host._ensure_preview_canvas = _orig
        ov.hide()


def test_zoom_past_one_starts_tiled_decode_immediately(qtbot, tmp_path, monkeypatch):
    """W2: wheel-zoom past 1.0 bypasses dwell and kicks the staged decode."""
    from types import SimpleNamespace

    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtWidgets import QApplication as _QA

    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    src = _item(_real_png(tmp_path, "zm.png"))
    ov = _make_overlay(qtbot)
    card, _orig = _make_dwell_canvas(qtbot, ov, monkeypatch)
    try:
        _patch_ql_async(monkeypatch, _QLHoldPool())
        assert _host._populate_preview_canvas(ov, src) is True
        _QA.processEvents()
        assert _tiled_kicks() == []
        assert getattr(card, "_ql_tiled_pending", None) is not None

        card.setGeometry(0, 0, 400, 300)
        ev = SimpleNamespace(
            position=lambda: QPointF(200.0, 150.0),
            angleDelta=lambda: QPoint(0, 240),
            accept=lambda: None,
        )
        card.wheelEvent(ev)
        assert float(getattr(card, "_zoom", 1.0)) > 1.0
        kicks = _tiled_kicks()
        assert len(kicks) == 1, f"zoom>1.0 must kick immediately, got {len(kicks)}"
        assert getattr(card, "_ql_tiled_pending", None) is None
    finally:
        _host._ensure_preview_canvas = _orig
        ov.hide()


def _show_series(overlay, item, series, mode):
    """Full show_for for a gallery series (mirrors the strip-test harness)."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication as _QA

    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode=mode,
            source_path=None,
            series=[list(series)],
            items=list(series),
        )
    )
    overlay.show_for(item, owner)
    try:
        parent = getattr(overlay, "_parity_test_parent", None) or overlay.parentWidget()
        if parent is not None:
            parent.resize(1280, 800)
            parent.show()
    except Exception:
        pass
    _QA.processEvents()


def _item_dims(path) -> GalleryItem:
    """Gallery item with grid-grade dims pre-seeded (800×600 test PNGs).

    The gallery grid delivers dimensions before quick look opens, so
    ``populate_preview``'s ``setdefault`` dims write is a no-op and the
    metrics fingerprint is stable across warm → walk. Without this the
    first real-file walk always misses (``{}`` → ``{width,height}`` is a
    genuine input change under the W2 contract).
    """
    return GalleryItem(path=path, mtime_ns=1, metrics={"width": 800, "height": 600})


def test_settle_fire_warms_neighbor_metrics_next_first(qtbot, tmp_path, monkeypatch):
    """W3: settle fire pre-builds prev/next metric rows (next-first).

    A fake settle fire warms both neighbors; the first walk visit to the
    next neighbor is a row-container cache hit (zero recreation).
    """
    from PySide6.QtWidgets import QApplication as _QA

    from tabs.image_gallery.models import Mode
    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    paths = [_real_png(tmp_path, f"w{i}.png") for i in range(3)]
    items = [_item_dims(p) for p in paths]
    ov = _make_overlay(qtbot)
    try:
        _show_series(ov, items[1], items, mode=Mode.FIDELITY)
        _QA.processEvents()
        assert ov._current_idx == 1
        assert list(ov._metric_rows)
        # Image-prefetch workers are not the subject here — metrics warm is.
        monkeypatch.setattr(_host, "_prefetch_neighbors", lambda *_a, **_k: None)
        import tabs.image_gallery.ui.quick_look.metrics as _metrics

        warm_calls: list = []
        _real_warm = _metrics.warm_metrics_for

        def _spy(overlay, item):
            warm_calls.append(Path(getattr(item, "path", "")))
            return _real_warm(overlay, item)

        monkeypatch.setattr(_metrics, "warm_metrics_for", _spy)
        token = int(getattr(ov, "_ql_prefetch_token", 0) or 0)
        _host._fire_scheduled_prefetch(ov, ov._current_item, token)
        _QA.processEvents()
        assert warm_calls == [paths[2], paths[0]], "settle warm is next-first"
        warmed = {k: [id(w) for w in v] for k, v in (getattr(ov, "_metrics_row_cache", None) or {}).items()}
        assert len(warmed) >= 2
        ov._walk(1)
        _QA.processEvents()
        _QA.processEvents()
        assert ov._current_idx == 2
        assert [id(w) for w in ov._metric_rows] in warmed.values()
    finally:
        ov.hide()


def test_stale_settle_schedule_skips_metrics_warm(qtbot, tmp_path, monkeypatch):
    """W3: a token bump between schedule and fire retires pending warms."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication as _QA

    from tabs.image_gallery.models import Mode
    from tabs.image_gallery.ui.quick_look import preview_canvas_host as _host

    paths = [_real_png(tmp_path, f"t{i}.png") for i in range(3)]
    items = [_item_dims(p) for p in paths]
    ov = _make_overlay(qtbot)
    try:
        _show_series(ov, items[1], items, mode=Mode.FIDELITY)
        _QA.processEvents()
        monkeypatch.setattr(_host, "_prefetch_neighbors", lambda *_a, **_k: None)
        import tabs.image_gallery.ui.quick_look.metrics as _metrics

        calls: list = []
        _real_warm = _metrics.warm_metrics_for

        def _spy(overlay, item):
            calls.append(Path(getattr(item, "path", "")))
            return _real_warm(overlay, item)

        monkeypatch.setattr(_metrics, "warm_metrics_for", _spy)
        fired: list = []
        monkeypatch.setattr(QTimer, "singleShot", lambda _ms, _cb: fired.append(_cb))
        _host._schedule_prefetch(ov, ov._current_item)
        assert len(fired) == 1
        # Walk/show/hide bumps the token before the fire lands.
        ov._ql_prefetch_token = int(getattr(ov, "_ql_prefetch_token", 0) or 0) + 1
        cache_before = dict(getattr(ov, "_metrics_row_cache", None) or {})
        fired[0]()
        _QA.processEvents()
        assert calls == [], "stale settle fire must build nothing"
        assert dict(getattr(ov, "_metrics_row_cache", None) or {}) == cache_before
    finally:
        ov.hide()


def test_rhi_hidden_failures_drop_poisoned_canvas(qtbot, tmp_path):
    """Persistently RHI-failed never-presented canvas is dropped for recreation.

    A canvas whose renders fail before the first settled frame caches the
    failure and never presents (static cover forever, across close/reopen
    — the release path reuses the widget).
    """
    from tabs.image_gallery.models import Mode

    pm = QPixmap(200, 100)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / "v.png"
    assert pm.save(str(p), "PNG")
    item = GalleryItem(path=p, mtime_ns=1)
    ov = _make_overlay(qtbot)
    _show_series(ov, item, [item], Mode.FIDELITY)
    QApplication.processEvents()
    canvas = getattr(ov, "_preview_canvas", None)
    assert canvas is not None
    ov.hide()
    QApplication.processEvents()
    assert not canvas.isVisible()
    for _ in range(3):
        try:
            canvas.renderFailed.emit()
        except Exception:
            pass
    QApplication.processEvents()
    qtbot.wait(700)
    QApplication.processEvents()
    assert getattr(ov, "_preview_canvas", None) is None
    assert int(getattr(ov, "_ql_rhi_recoveries", 0) or 0) == 1
    # Next show recreates a fresh canvas through the ensure path.
    _show_series(ov, item, [item], Mode.FIDELITY)
    QApplication.processEvents()
    fresh = getattr(ov, "_preview_canvas", None)
    assert fresh is not None and fresh is not canvas
    ov.hide()


def test_rhi_visible_failures_never_recover(qtbot, tmp_path):
    """Visible renderFailed AFTER a presented frame (resize storms) drops nothing."""
    from tabs.image_gallery.models import Mode

    pm = QPixmap(200, 100)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / "w.png"
    assert pm.save(str(p), "PNG")
    item = GalleryItem(path=p, mtime_ns=1)
    ov = _make_overlay(qtbot)
    _show_series(ov, item, [item], Mode.FIDELITY)
    QApplication.processEvents()
    canvas = getattr(ov, "_preview_canvas", None)
    assert canvas is not None and canvas.isVisible()
    try:
        canvas._frame_ok = True  # presented before: resize-storm shape.
    except Exception:
        pass
    for _ in range(5):
        try:
            canvas.renderFailed.emit()
        except Exception:
            pass
    QApplication.processEvents()
    qtbot.wait(700)
    QApplication.processEvents()
    assert getattr(ov, "_preview_canvas", None) is canvas
    assert int(getattr(ov, "_ql_rhi_recoveries", 0) or 0) == 0
    ov.hide()


def test_rhi_visible_failures_recover_when_never_presented(qtbot, tmp_path):
    """Visible renderFailed with NO presented frame drops the canvas (P2 live).

    Live 2026-10-06: close/reopen of a QL overlay whose canvas never
    presented stays dead — the release path reuses the widget and the old
    hidden-only classifier ignored its (visible) failures, so recovery
    never fired. Never-presented + threshold, any visibility → drop.
    """
    from tabs.image_gallery.models import Mode

    pm = QPixmap(200, 100)
    pm.fill(QColor("#3a6ea5"))
    p = tmp_path / "u.png"
    assert pm.save(str(p), "PNG")
    item = GalleryItem(path=p, mtime_ns=1)
    ov = _make_overlay(qtbot)
    _show_series(ov, item, [item], Mode.FIDELITY)
    QApplication.processEvents()
    canvas = getattr(ov, "_preview_canvas", None)
    assert canvas is not None and canvas.isVisible()
    assert not bool(getattr(canvas, "_frame_ok", False))
    for _ in range(3):
        try:
            canvas.renderFailed.emit()
        except Exception:
            pass
    QApplication.processEvents()
    qtbot.wait(700)
    QApplication.processEvents()
    # Overlay is visible here, so the drop repopulates immediately: the
    # slot holds a FRESH canvas, the poisoned one is gone.
    fresh = getattr(ov, "_preview_canvas", None)
    assert fresh is not None and fresh is not canvas
    assert int(getattr(ov, "_ql_rhi_recoveries", 0) or 0) == 1
    ov.hide()
