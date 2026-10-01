"""Quick-look demand pyramid: sharp zoom on zoom>1.0 or dwell (QL sharp-zoom).

Covers the demand-built full pyramid in ``preview_canvas`` + the host
source-path wiring:

- zoomed raster samples the finer level when the pyramid is ready (fake
  levels, no GPU — blue level pixels win over the red coarse);
- no-zoom path is pixel-identical with or without a ready pyramid;
- walk-away aborts the decode (stale result closes, no pyramid kept) and
  the level build (generation-wired abort, no levels added after release);
- oversize/untracked sources stay coarse-only (no worker ever spawned);
- dwell fires only for the live item; plain widgets never build;
- host hands the path over on both populate paths and the walk release
  retires the demand state while keeping coarse memos open.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas as pc
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host


@pytest.fixture(autouse=True)
def _no_dwell(monkeypatch):
    """Dwell timers must never fire mid-suite (stray thread decodes)."""
    monkeypatch.setattr(pc, "_QL_DWELL_MS", 3600000)


def _png(tmp_path: Path, name: str, color: str, w: int = 800, h: int = 600) -> Path:
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    p = tmp_path / name
    assert pm.save(str(p), "PNG")
    return p


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=1, metrics={})


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent
    return ov


def _make_canvas(qtbot, coarse):
    card = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    card.resize(640, 480)
    card.set_source(coarse)
    return card


def _target(w: int = 400, h: int = 300):
    return SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: w, height=lambda: h)
    )


def _mean_rgb_frame(frame) -> tuple[float, float, float]:
    _, _, px = frame
    n = len(px) // 4
    r = sum(px[i] for i in range(0, len(px), 4)) / n
    g = sum(px[i] for i in range(1, len(px), 4)) / n
    b = sum(px[i] for i in range(2, len(px), 4)) / n
    return r, g, b


class _Sig:
    def __init__(self) -> None:
        self.cbs: list = []
        self.emitted: list = []

    def connect(self, cb) -> None:
        self.cbs.append(cb)

    def emit(self, *args) -> None:
        self.emitted.append(args)


class _FakeWorker:
    """GenericWorker double: captures fn, fires slots synchronously."""

    instances: list = []

    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        # Same signal names as the real GenericWorker (the coordinator
        # touches partial_result at start_build time).
        self.signals = SimpleNamespace(
            result=_Sig(), finished=_Sig(), partial_result=_Sig(), error=_Sig()
        )
        _FakeWorker.instances.append(self)


class _FakePool:
    def __init__(self) -> None:
        self.workers: list = []

    def start(self, worker) -> None:
        self.workers.append(worker)


@pytest.fixture()
def _fake_async(monkeypatch):
    import sli_ui_toolkit.workers as _wmod

    _FakeWorker.instances.clear()
    pool = _FakePool()
    monkeypatch.setattr(_wmod, "GenericWorker", _FakeWorker)
    monkeypatch.setattr(
        QThreadPool, "globalInstance", classmethod(lambda cls: pool)
    )
    # A source LARGER than the view: the lazy gate (need>0) lets the
    # trigger through. The real decode still reads the small test png —
    # only the probe (trigger input) is faked.
    monkeypatch.setattr(
        _preview, "_fast_image_size", lambda _p: (3200, 2400)
    )
    return pool


def _blue_level(calls: list):
    def _best(box, scale):
        calls.append((tuple(box), float(scale)))
        left, top, right, bottom = (int(v) for v in box)
        img = QImage(max(1, right - left), max(1, bottom - top),
                     QImage.Format.Format_RGBA8888)
        img.fill(QColor("#2244cc"))
        return img

    return _best


# -- LOD raster ---------------------------------------------------------------

def test_zoomed_raster_samples_finer_level(qtbot, tmp_path):
    """Zoom 2x with a ready pyramid: best_pixels wins, blue level shown."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        calls: list = []
        card._ql_full_store = SimpleNamespace(is_open=True, size=(800, 600))
        card._ql_pyramid = SimpleNamespace(
            valid=True, level_count=3, is_complete=lambda: False,
            best_pixels=_blue_level(calls), close=lambda: None,
        )
        card._zoom = 2.0
        card._frame_key = None

        frame = card._raster_frame(_target())
        assert frame is not None
        assert (frame[0], frame[1]) == (400, 300)
        assert calls, "zoomed raster must sample the pyramid level"
        box, scale = calls[0]
        left, top, right, bottom = box
        assert 0 <= left < right <= 800 and 0 <= top < bottom <= 600
        assert abs(scale - 1.0) < 1e-6, f"display-px per full-px at 2x, got {scale}"
        r, g, b = _mean_rgb_frame(frame)
        assert b > r, f"level (blue) pixels must win, got {(r, g, b)}"

        # Coarse-only control: same zoom, red upscale wins instead.
        card._ql_pyramid = None
        card._ql_full_store = None
        card._frame_key = None
        plain = card._raster_frame(_target())
        assert plain is not None
        pr, _, pb = _mean_rgb_frame(plain)
        assert pr > pb, f"coarse fallback must stay red, got {(pr, pb)}"
        assert plain[2] != frame[2], "LOD frame must differ from the coarse upscale"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_no_zoom_path_unchanged_with_pyramid_ready(qtbot, tmp_path):
    """Zoom 1.0: pyramid present or not, pixels are bit-identical."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        calls: list = []
        card._ql_full_store = SimpleNamespace(is_open=True, size=(800, 600))
        card._ql_pyramid = SimpleNamespace(
            valid=True, level_count=3, is_complete=lambda: True,
            best_pixels=_blue_level(calls), close=lambda: None,
        )
        card._zoom = 1.0
        card._frame_key = None
        with_pyramid = card._raster_frame(_target())
        assert with_pyramid is not None

        card._ql_pyramid = None
        card._ql_full_store = None
        card._frame_key = None
        without = card._raster_frame(_target())
        assert without is not None

        assert calls == [], "no-zoom path must never touch pyramid levels"
        assert with_pyramid == without, "no-zoom pixels must be bit-identical"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_lod_miss_falls_back_to_coarse(qtbot, tmp_path):
    """Zoomed but level unreadable: today's path, no raise, red pixels."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        card._ql_full_store = SimpleNamespace(is_open=True, size=(800, 600))
        card._ql_pyramid = SimpleNamespace(
            valid=True, level_count=3, is_complete=lambda: False,
            best_pixels=lambda _box, _scale: None, close=lambda: None,
        )
        card._zoom = 3.0
        card._frame_key = None
        frame = card._raster_frame(_target())
        assert frame is not None
        r, _, b = _mean_rgb_frame(frame)
        assert r > b, f"miss must fall back to the red coarse, got {(r, b)}"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


# -- demand trigger / abort ---------------------------------------------------

def test_zoom_past_built_holds_coarse_and_kicks_build(qtbot, tmp_path, _fake_async):
    """Deep zoom with no levels yet: coarse holds AND the build is requested.

    Requested, not completed: the decode worker is captured in the pool
    while no pyramid materialized on the canvas.
    """
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        card.note_ql_source(str(red))
        card._zoom = 3.0
        card._frame_key = None
        frame = card._raster_frame(_target())
        assert frame is not None
        r, _, b = _mean_rgb_frame(frame)
        assert r > b, f"unbuilt levels must hold the red coarse, got {(r, b)}"

        assert card._maybe_demand_build("zoom") is True
        assert len(_fake_async.workers) == 1, "the missing level must be requested"
        assert card._ql_pyramid is None, "nothing may complete synchronously"
        assert card._ql_need > 0
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_lazy_cap_builds_only_to_need(qtbot, tmp_path, _fake_async):
    """Resume requests the build; the shared loop stops at need (incomplete).

    4096px base at 1.5x in a 1600x1200 fb needs level 1 only: the resume
    is requested (worker captured, nothing completed), and driving the
    shared ``_pyramid_build_loop`` with the canvas abort predicate builds
    exactly L1 — never ``build_all`` (the pyramid stays incomplete).
    """
    from PIL import Image as _PILImage

    from engine.store.pyramid_pixel_store import PyramidPixelStore
    from engine.store.tiled_pixel_store import TiledPixelStore
    from engine.pyramid.coordinator import _pyramid_build_loop

    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    full = None
    try:
        card = _make_canvas(qtbot, coarse)
        pil = _PILImage.new("RGBA", (4096, 4096), (180, 60, 60, 255))
        full = TiledPixelStore.from_pil(pil)
        pyr = PyramidPixelStore(full)
        card._ql_full_store = full
        card._ql_pyramid = pyr
        card._zoom = 1.5
        card._last_fb = (1600, 1200)
        gen = int(card._ql_gen)

        assert card._ql_resume_build(full, gen) is True
        assert len(_fake_async.workers) == 1, "level build must be requested"
        assert pyr.level_count == 1, "nothing may complete synchronously"
        assert int(card._ql_need) == 1

        seen: list = []
        _pyramid_build_loop(pyr, card._ql_abort_fn(full, gen), 12345, 3,
                            progress_callback=seen.append)
        assert pyr.level_count == 2, "exactly the needed level lands"
        assert pyr.is_complete() is False, "never build_all past the need"
        assert len(seen) == 1 and seen[0][3] is False
        assert card._ql_abort_fn(full, gen)() is True, "target landed — stop"
    finally:
        try:
            coarse.close()
        except Exception:
            pass
        if full is not None:
            try:
                full.close()
            except Exception:
                pass

def test_walk_away_aborts_decode_no_materials(qtbot, tmp_path, _fake_async):
    """Decode lands after the walk: store closed, no pyramid installed."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        card.note_ql_source(str(red))
        assert card._maybe_demand_build("test") is True
        assert card._ql_decoding is True
        assert len(_fake_async.workers) == 1
        worker = _fake_async.workers[0]

        store = worker.fn(*worker.args, **worker.kwargs)
        assert store is not None and store.is_open

        card.clear_source()  # the walk lands before the result does.
        for cb in worker.signals.result.cbs:
            cb(store)
        assert not store.is_open, "superseded decode must be closed"
        assert card._ql_pyramid is None
        assert card._ql_full_store is None
        assert card._ql_coord is None, "no level build may start after release"
        for cb in worker.signals.finished.cbs:
            cb()
        assert card._ql_decoding is False
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_live_decode_installs_pyramid_and_walk_closes_it(qtbot, tmp_path, _fake_async):
    """Live item: decode installs the pyramid; the walk closes everything."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        card.note_ql_source(str(red))
        assert card._maybe_demand_build("test") is True
        worker = _fake_async.workers[0]
        store = worker.fn(*worker.args, **worker.kwargs)
        assert store is not None
        for cb in worker.signals.result.cbs:
            cb(store)
        assert card._ql_full_store is store
        assert card._ql_pyramid is not None
        assert bool(card._ql_pyramid.valid) is True
        assert store.is_open
        for cb in worker.signals.finished.cbs:
            cb()
        assert card._ql_decoding is False

        card.clear_source()
        assert card._ql_pyramid is None
        assert card._ql_full_store is None
        assert not store.is_open, "walk must close the private full store"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_level_build_aborts_on_generation_bump(qtbot, tmp_path):
    """Level stage: post-walk abort adds no levels (real PyramidPixelStore)."""
    from PIL import Image as _PILImage

    from engine.store.pyramid_pixel_store import PyramidPixelStore
    from engine.store.tiled_pixel_store import TiledPixelStore

    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    full = None
    try:
        card = _make_canvas(qtbot, coarse)
        pil = _PILImage.new("RGBA", (2048, 2048), (180, 60, 60, 255))
        full = TiledPixelStore.from_pil(pil)
        pyr = PyramidPixelStore(full)
        card._ql_full_store = full
        card._ql_pyramid = pyr
        gen = int(card._ql_gen)
        # Simulate the zoom that demanded level 1 (the lazy target the
        # abort predicate is capped by).
        card._ql_need = 1
        abort = card._ql_abort_fn(full, gen)
        assert abort() is False, "live build must not abort"

        card.clear_source()  # the walk: bump + close private materials.
        assert abort() is True, "post-walk predicate must abort"
        assert pyr.build_next_level(should_abort=abort) is False
        assert pyr.level_count == 1, "no pyramid materials after release"
        assert not full.is_open

        # Positive control: an un-aborted build adds exactly one level.
        full2 = TiledPixelStore.from_pil(pil)
        try:
            pyr2 = PyramidPixelStore(full2)
            assert pyr2.build_next_level(should_abort=lambda: False) is True
            assert pyr2.level_count == 2
            assert pyr2.is_complete() is True
        finally:
            try:
                pyr2.close()
            except Exception:
                pass
            try:
                full2.close()
            except Exception:
                pass
    finally:
        try:
            coarse.close()
        except Exception:
            pass
        if full is not None:
            try:
                full.close()
            except Exception:
                pass


def test_dwell_fires_only_for_live_item(qtbot, tmp_path, _fake_async):
    """Dwell pre-warms the shown item; a stale timer builds nothing."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        card.note_ql_source(str(red))
        gen = int(card._ql_gen)
        card._ql_on_dwell(gen)
        assert len(_fake_async.workers) == 1, "live dwell must trigger the build"
        card._ql_on_dwell(gen + 99)
        assert len(_fake_async.workers) == 1, "stale dwell must build nothing"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_no_path_never_builds(qtbot, tmp_path, _fake_async):
    """A canvas the host never gave a path to (or retired) builds nothing."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        assert card._maybe_demand_build("test") is False
        assert _fake_async.workers == []
    finally:
        try:
            coarse.close()
        except Exception:
            pass


# -- caps ---------------------------------------------------------------------

def test_oversize_source_stays_coarse_only(qtbot, tmp_path, monkeypatch, _fake_async):
    """9000px source: no worker, coarse-only flag, raster still serves."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        monkeypatch.setattr(_preview, "_fast_image_size", lambda _p: (9000, 7000))
        card.note_ql_source(str(red))
        assert card._maybe_demand_build("zoom") is False
        assert card._ql_coarse_only is True
        assert _fake_async.workers == [], "oversize must never spawn a decode"
        assert card._ql_pyramid is None
        card._zoom = 4.0
        card._frame_key = None
        frame = card._raster_frame(_target())
        assert frame is not None, "raster must still serve the coarse path"
    finally:
        try:
            coarse.close()
        except Exception:
            pass


def test_untracked_source_stays_coarse_only(qtbot, tmp_path, monkeypatch, _fake_async):
    """Unmeasurable dims (None probe): fail open to coarse-only."""
    red = _png(tmp_path, "red.png", "#c0392b")
    coarse = host._coarse_store_for(str(red))
    assert coarse is not None
    try:
        card = _make_canvas(qtbot, coarse)
        monkeypatch.setattr(_preview, "_fast_image_size", lambda _p: None)
        card.note_ql_source(str(red))
        assert card._maybe_demand_build("zoom") is False
        assert card._ql_coarse_only is True
        assert _fake_async.workers == []
    finally:
        try:
            coarse.close()
        except Exception:
            pass


# -- host lifetimes -----------------------------------------------------------

class _NotingCanvas(QWidget):
    """Canvas double: records set_source + the demand source path."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sources: list = []
        self.cleared = 0
        self.ql_paths: list = []

    def set_source(self, store) -> None:
        self.sources.append(store)

    def clear_source(self) -> None:
        self.cleared += 1

    def note_ql_source(self, path) -> None:
        self.ql_paths.append(str(path))


def test_host_hands_path_and_walk_retires_demand(qtbot, tmp_path):
    """Populate hands the path (hit + miss); walk clears, memos stay open."""
    red = _png(tmp_path, "red.png", "#c0392b")
    blue = _png(tmp_path, "blue.png", "#3a6ea5")
    ov = _make_overlay(qtbot)
    fake = _NotingCanvas()
    import tabs.image_gallery.ui.quick_look.preview_canvas_host as _host

    orig_ensure = _host._ensure_preview_canvas
    try:
        # Mirror _ensure_preview_canvas: the slot owns the live canvas ref
        # so the walk/overlay release reaches it via overlay._preview_canvas.
        ov._preview_canvas = fake
        _host._ensure_preview_canvas = lambda _ov: fake
        assert _host._populate_preview_canvas(ov, _item(red)) is True
        assert fake.ql_paths == [str(red)], "miss path must hand the source path"
        ov._release_preview_resources(for_walk=True)
        QApplication.processEvents()
        assert fake.cleared == 1

        assert _host._populate_preview_canvas(ov, _item(blue)) is True
        assert fake.ql_paths == [str(red), str(blue)]
        ov._release_preview_resources(for_walk=True)
        QApplication.processEvents()

        # Walk back: memo hands the SAME store, path handed again, no decode.
        assert _host._populate_preview_canvas(ov, _item(red)) is True
        assert fake.ql_paths == [str(red), str(blue), str(red)]
        assert ov._preview_store is fake.sources[0]

        ov._release_preview_resources()
        QApplication.processEvents()
        assert getattr(ov, "_preview_store_cache", {}) == {}
    finally:
        _host._ensure_preview_canvas = orig_ensure
        ov.hide()


def test_host_walk_releases_real_canvas_demand(qtbot, tmp_path):
    """Real canvas via populate: path noted, walk drops demand, memo open."""
    red = _png(tmp_path, "red.png", "#c0392b")
    ov = _make_overlay(qtbot)
    real = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(real)
    import tabs.image_gallery.ui.quick_look.preview_canvas_host as _host

    orig_ensure = _host._ensure_preview_canvas
    try:
        ov._preview_canvas = real
        # Mirror _ensure_preview_canvas fully: the memo probe is what keeps
        # clear_source from closing the memoized coarse store on walk.
        _host._install_memo_probe(ov, real)
        _host._ensure_preview_canvas = lambda _ov: real
        assert _host._populate_preview_canvas(ov, _item(red)) is True
        assert real._ql_source_path == str(red)
        live = ov._preview_store
        assert live is not None and live.is_open

        ov._release_preview_resources(for_walk=True)
        QApplication.processEvents()
        assert real._ql_source_path is None
        assert real._ql_pyramid is None
        assert real._ql_full_store is None
        assert live.is_open, "walk must keep the coarse memo open"

        ov._release_preview_resources()
        QApplication.processEvents()
        assert not live.is_open, "overlay release closes the coarse memo"
    finally:
        _host._ensure_preview_canvas = orig_ensure
        ov.hide()
