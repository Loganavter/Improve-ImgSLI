"""P2 engine: TilePrefetcher releases in-flight warms on every exit path.

Probes (behavioral, in-clone): GenericWorker emits ``finished`` even when
the warm raises, so today the release rides ``finished`` alone — one
signal flavor away from a permanent dedup leak. The prefetcher now
discards on BOTH finished and error (idempotent), sweeps entries older
than the timeout, and guards the set with a lock (slots fire on the GUI
thread while warm() may come from the render thread).
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

import engine.gpu.tile_prefetch as prefetch_mod
from engine.gpu.tile_prefetch import TilePrefetcher

app = QApplication.instance() or QApplication(["x", "-platform", "offscreen"])


def _settle(pf, timeout_s=5.0):
    deadline = time.time() + timeout_s
    while len(pf) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return len(pf)


def _region():
    return SimpleNamespace(left=0, top=0, right=16, bottom=16)


def test_error_path_discards_and_rearms(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("store closed mid-warm")

    monkeypatch.setattr(prefetch_mod, "crop_apron_tile", _boom)
    pf = TilePrefetcher()
    assert pf.warm("k", (0, 0), object(), _region(), 0) is True
    # Same tile while in flight dedups.
    assert pf.warm("k", (0, 0), object(), _region(), 0) is False
    assert _settle(pf) == 0
    # Error released the entry: the tile can warm again.
    monkeypatch.setattr(prefetch_mod, "crop_apron_tile", lambda *a, **k: None)
    assert pf.warm("k", (0, 0), object(), _region(), 0) is True
    assert _settle(pf) == 0


def test_success_path_discards(monkeypatch):
    seen = []
    monkeypatch.setattr(
        prefetch_mod, "crop_apron_tile", lambda *a, **k: seen.append(True)
    )
    pf = TilePrefetcher()
    assert pf.warm("k", (1, 2), object(), _region(), 0) is True
    assert _settle(pf) == 0
    assert seen, "warm body must actually run off-thread"


def test_none_source_never_submits():
    pf = TilePrefetcher()
    assert pf.warm("k", (0, 0), None, _region(), 0) is False
    assert len(pf) == 0


def test_sweep_drops_stale_entries():
    pf = TilePrefetcher(timeout_s=30.0)
    pf._in_flight[("old", (0, 0))] = time.monotonic() - 60.0
    pf._in_flight[("new", (0, 0))] = time.monotonic()
    assert pf.sweep() == 1
    assert list(pf._in_flight) == [("new", (0, 0))]
    assert pf.sweep(timeout_s=0.0) == 1
    assert len(pf) == 0


def test_concurrent_warm_is_thread_safe(monkeypatch):
    monkeypatch.setattr(prefetch_mod, "crop_apron_tile", lambda *a, **k: None)
    pf = TilePrefetcher()
    results = {}

    def _warm(i):
        results[i] = pf.warm("k", (i, 0), object(), _region(), 0)

    threads = [threading.Thread(target=_warm, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(results.values()), "distinct keys must all submit"
    assert _settle(pf) == 0
