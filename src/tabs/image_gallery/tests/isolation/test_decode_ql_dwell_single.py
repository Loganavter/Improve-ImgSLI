"""One full decode per shown item on the Quick Look dwell path (owner invariant I2).

Audit R4: ``QuickLookCanvasWidget._ql_on_dwell`` fired TWO full decodes of the
SAME file in one timer callback — the demand/pyramid decode
(``services.decode_policy.QL_FULL_EDGE_CAP`` = 8192, canvas-private) AND the
staged uncapped tiled decode (``preview_canvas_host/tiled_source.py``). Both
stores are the same file at full resolution; only one is needed.

The contract pinned here, on the seam the two consumers actually share:

1. the demand decode is the one full decode (measured: 2 before the change,
   ``TiledPixelStore.from_path`` (via ``decode_full_store``) reached once);
2. the tiled consumer is NOT silently disabled — when the demand store lands it
   IS the canvas's tiled source (same object, full resolution), so a deep zoom
   (level 0 = the full-res store) is served without re-opening the file;
3. when the demand path cannot serve (source over the 8192 cap → coarse-only),
   the staged tiled kick still fires exactly once (uncapped) — that is the
   path kept for zoom levels beyond the demand cap.

Both routes assert ONE decode for the shown item; the difference is which
consumer bought it. No GPU is needed: the tiled binding is inspected as the
canvas's declared inputs (``_tiled_source`` / ``_ql_bound_levels``), never
pixels.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PIL")

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QWidget

import engine.cache.pyramid_demand as _demand
from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas as pc
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host
from tabs.image_gallery.ui.quick_look.preview import _stash_cache_key


#: Larger than the 640x480 viewport, so zoom 1.0 already demands a level
#: (``_ql_needed_level(...) > 0``) and the dwell decode really starts.
FULL = (1600, 1200)


@pytest.fixture(autouse=True)
def _no_real_dwell(monkeypatch):
    """Arm no real 1.2 s dwell timer: the test calls ``_ql_on_dwell`` itself."""
    from tabs.image_gallery.ui.quick_look.preview_canvas import lazy_levels

    monkeypatch.setattr(lazy_levels, "_QL_DWELL_MS", 3_600_000)


class _Sig:
    def __init__(self) -> None:
        self.cbs: list = []

    def connect(self, cb) -> None:
        self.cbs.append(cb)

    def emit(self, *args) -> None:
        for cb in list(self.cbs):
            cb(*args)


class _FakeWorker:
    """``GenericWorker`` double: captures the callable, never runs it."""

    instances: list = []

    def __init__(self, fn, *args, **kwargs) -> None:
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = SimpleNamespace(
            result=_Sig(), finished=_Sig(), partial_result=_Sig(), error=_Sig()
        )
        _FakeWorker.instances.append(self)


class _FakePool:
    """Captures workers so the test decides when a decode actually lands."""

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
    monkeypatch.setattr(QThreadPool, "globalInstance", classmethod(lambda cls: pool))
    return pool


class _DecodeSpy:
    """Counts the two full-decode entry points, per resolved path."""

    def __init__(self, monkeypatch) -> None:
        self.decodes: list[tuple[str, object]] = []
        self.store_opens: dict[str, int] = {}
        real_decode = _demand.decode_full_store
        real_from_path = TiledPixelStore.from_path

        def _key(target) -> str:
            try:
                return str(Path(target).resolve())
            except Exception:
                return "<other>"

        def _counted_decode(path, *, cap_edge=None, tmp_dir=None):
            self.decodes.append((_key(path), cap_edge))
            return real_decode(path, cap_edge=cap_edge, tmp_dir=tmp_dir)

        def _counted_from_path(path, *a, **k):
            k_ = _key(path)
            self.store_opens[k_] = self.store_opens.get(k_, 0) + 1
            return real_from_path(path, *a, **k)

        monkeypatch.setattr(_demand, "decode_full_store", _counted_decode)
        monkeypatch.setattr(
            TiledPixelStore, "from_path", staticmethod(_counted_from_path)
        )

    def decodes_for(self, path: Path) -> list:
        key = str(Path(path).resolve())
        return [cap for p, cap in self.decodes if p == key]


def _png(tmp_path: Path, name: str, color: str = "#c0392b") -> Path:
    pm = QPixmap(*FULL)
    pm.fill(QColor(color))
    path = tmp_path / name
    assert pm.save(str(path), "PNG")
    return path


def _make_canvas(qtbot, path: Path):
    """Real canvas fed the bounded coarse store, exactly like the host does."""
    card = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    card.resize(640, 480)
    coarse = host._coarse_store_for(str(path))
    assert coarse is not None
    card.set_source(coarse)
    return card


class _OverlayDouble:
    """Minimal host overlay: weak-referenceable + the memo dicts the host owns."""

    def __init__(self, canvas) -> None:
        self._preview_canvas = canvas
        self._ql_tiled_store_cache: dict = {}


def _overlay_for(card):
    return _OverlayDouble(card)


def _run_demand_worker(store_out: list) -> None:
    """Run the captured demand decode worker and deliver its result."""
    for worker in list(_FakeWorker.instances):
        if getattr(worker.fn, "__name__", "") != "decode_full":
            continue
        out = worker.fn(*worker.args, **worker.kwargs)
        store_out.append(out)
        worker.signals.result.emit(out)


def test_dwell_decodes_the_shown_item_once_and_tiled_reuses_that_store(
    qtbot, tmp_path, monkeypatch, _fake_async
):
    """Dwell: one full decode; the tiled source IS the demand store."""
    src = _png(tmp_path, "dwell.png")
    spy = _DecodeSpy(monkeypatch)
    card = _make_canvas(qtbot, src)
    overlay = _overlay_for(card)
    try:
        card.note_ql_source(str(src))
        key = _stash_cache_key(str(src))
        # Exactly what the host does on show (dwell-gated: stages, no decode).
        host._arm_tiled_dwell(overlay, card, src, key)
        assert card._ql_tiled_pending is not None
        assert spy.decodes_for(src) == [], "a plain show must decode nothing"

        gen = int(card._ql_gen)
        card._ql_on_dwell(gen)

        # The demand decode is the ONE full decode the callback bought.
        assert card._ql_decoding is True
        demand_workers = [
            w
            for w in _FakeWorker.instances
            if getattr(w.fn, "__name__", "") == "decode_full"
        ]
        assert len(demand_workers) == 1, "dwell must request the demand decode"
        tiled_kicks = [
            w for w in _FakeWorker.instances if w.fn is host._decode_full_store_uncapped
        ]
        assert tiled_kicks == [], (
            "dwell must not ALSO kick the uncapped tiled decode for the same file"
        )

        landed: list = []
        _run_demand_worker(landed)
        assert len(landed) == 1 and landed[0] is not None
        full = landed[0]

        # ONE full-resolution decode for the shown item (red-before: 2).
        assert spy.decodes_for(src) == [pc._QL_FULL_EDGE_CAP], (
            "the shown item must be decoded once on the dwell path, got "
            f"{spy.decodes_for(src)} (from_path={spy.store_opens})"
        )
        assert spy.store_opens[str(src.resolve())] == 1

        # Non-vacuity: the tiled consumer was served, not disabled. It holds
        # the SAME store (full resolution, not the coarse) and its LOD inputs
        # are that store's pyramid — level 0 == the full-res store.
        assert card._ql_full_store is full and full.is_open
        assert card._tiled_source == (key, full), (
            f"tiled source must reuse the demand store, got {card._tiled_source}"
        )
        assert card._ql_tiled_pending is None, "the staged kick was consumed once"
        assert full.size == FULL
        levels = card._ql_bound_levels(key)
        assert levels, "the tiled view needs at least the level-0 store"
        assert levels[-1][1] is full, "finest/last tiled level must be level 0"

        # A deep zoom resolves to level 0 = the full-res store the tiled path
        # already holds: no second open, the tiled source still answers.
        zoom = 8.0
        assert card._ql_needed_level(640, 480, FULL[0], FULL[1], zoom) == 0
        assert card._ql_full_store is full
        assert spy.decodes_for(src) == [pc._QL_FULL_EDGE_CAP], (
            "a deep zoom re-opened the file instead of using the held store"
        )

        # Walk ownership: the aliasing tiled source is retired before the
        # private store closes — a closed store is never left registered.
        card.clear_source()
        assert card._tiled_source is None
        assert not full.is_open
        assert spy.decodes_for(src) == [pc._QL_FULL_EDGE_CAP]
    finally:
        card.clear_source()


def test_dwell_falls_back_to_the_tiled_decode_when_demand_cannot_serve(
    qtbot, tmp_path, monkeypatch, _fake_async
):
    """Over the demand cap: the tiled (uncapped) path still fires exactly once."""
    from tabs.image_gallery.ui.quick_look.preview_canvas import lazy_levels

    src = _png(tmp_path, "big.png")
    spy = _DecodeSpy(monkeypatch)
    # A source over the demand cap stays coarse-only; the tiled path is the
    # one that keeps full resolution for deep zooms (audit: never disabled).
    monkeypatch.setattr(lazy_levels, "_QL_FULL_EDGE_CAP", 512)
    card = _make_canvas(qtbot, src)
    overlay = _overlay_for(card)
    try:
        card.note_ql_source(str(src))
        key = _stash_cache_key(str(src))
        host._arm_tiled_dwell(overlay, card, src, key)

        card._ql_on_dwell(int(card._ql_gen))

        assert card._ql_coarse_only is True, "over-cap must stay coarse-only"
        assert [
            w for w in _FakeWorker.instances if w.fn is host._decode_full_store_uncapped
        ], "the tiled path must still fire when the demand cap cannot serve"

        tiled_worker = next(
            w for w in _FakeWorker.instances if w.fn is host._decode_full_store_uncapped
        )
        store = tiled_worker.fn(*tiled_worker.args, **tiled_worker.kwargs)
        tiled_worker.signals.result.emit(store)
        assert store is not None and store.is_open
        assert spy.decodes_for(src) == [None], (
            "exactly one uncapped decode, got " f"{spy.decodes_for(src)}"
        )
        assert card._tiled_source == (key, store), "the tiled source must be installed"
        assert host._tiled_store_cache_lookup(overlay, key) is store
        assert spy.decodes_for(src) == [None], "registering the source re-decoded it"
    finally:
        card.clear_source()
        host._drop_tiled_store_cache(overlay)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
