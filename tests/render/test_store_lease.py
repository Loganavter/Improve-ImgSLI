"""StoreLease generation invalidation tests.

P2 lease parity: ``guard()`` is the single None-guard choke point every
tile entry point shares; mid-compute aborts (close between tiles, or a
read raising ``RuntimeError``) return ``None`` on every path — single and
threaded, highlight/grayscale/edge — instead of propagating torn state.
"""

from PIL import Image

from shared.image_processing.store_lease import StoreLease
from engine.store.tiled_pixel_store import TiledPixelStore


def test_lease_invalid_after_close():
    store = TiledPixelStore.from_pil(Image.new("RGBA", (32, 32), "red"))
    lease = StoreLease.capture(store)
    assert lease is not None
    assert lease.valid

    generation = store.generation
    store.close()

    assert not lease.valid
    assert store.generation == generation + 1
    assert lease.restore() is None


def test_worker_skips_stale_lease():
    store = TiledPixelStore.from_pil(Image.new("RGBA", (16, 16), "blue"))
    lease = StoreLease.capture(store)
    store.close()

    from engine.store.pixel_ops.unify import unify_pair

    img = Image.new("RGBA", (16, 16), "green")
    u1, u2 = unify_pair(store, img, lease1=lease, lease2=None)
    assert u1 is None and u2 is None


def test_guard_none_parity_and_capture_refusals():
    live = TiledPixelStore.from_pil(Image.new("RGBA", (8, 8), "red"))
    try:
        valid = StoreLease.capture(live)
        assert valid is not None
        assert StoreLease.guard() is True
        assert StoreLease.guard(None, None) is True
        assert StoreLease.guard(valid) is True
        assert StoreLease.guard(None, valid) is True
        assert StoreLease.any_stale(valid) is False
        assert StoreLease.capture(Image.new("RGBA", (8, 8), "red")) is None
        assert StoreLease.capture(None) is None
        live.close()
        assert StoreLease.guard(valid) is False
        assert StoreLease.guard(None, valid) is False
        assert StoreLease.any_stale(None, valid) is True
        assert valid.pinned() is None
    finally:
        try:
            live.close()
        except Exception:
            pass


def test_pinned_holds_store_across_window():
    store = TiledPixelStore.from_pil(Image.new("RGBA", (8, 8), "blue"))
    lease = StoreLease.capture(store)
    assert lease is not None
    assert lease.pinned() is store
    store.close()
    assert lease.pinned() is None


def _two_tile_stores():
    s1 = TiledPixelStore.from_pil(Image.new("RGBA", (1600, 100), "red"))
    s2 = TiledPixelStore.from_pil(Image.new("RGBA", (1600, 100), "blue"))
    return s1, s2


def test_highlight_aborts_when_store_closes_mid_compute(monkeypatch):
    import shared.analysis.diff_source as ds_mod

    monkeypatch.setattr(ds_mod, "_resolve_ssim_workers", lambda total: 1)
    s1, s2 = _two_tile_stores()
    lease1, lease2 = StoreLease.capture(s1), StoreLease.capture(s2)

    def _close_on_first_tile(payload):
        s1.close()

    try:
        result = ds_mod.create_highlight_diff_from_sources(
            s1, s2, lease1=lease1, lease2=lease2, progress_callback=_close_on_first_tile
        )
        assert result is None, "close between tiles must abort, not finalize"
    finally:
        for store in (s1, s2):
            try:
                store.close()
            except Exception:
                pass


def test_highlight_control_without_close_completes(monkeypatch):
    import shared.analysis.diff_source as ds_mod

    monkeypatch.setattr(ds_mod, "_resolve_ssim_workers", lambda total: 1)
    s1, s2 = _two_tile_stores()
    try:
        result = ds_mod.create_highlight_diff_from_sources(
            s1, s2, lease1=StoreLease.capture(s1), lease2=StoreLease.capture(s2)
        )
        assert result is not None
    finally:
        for store in (s1, s2):
            try:
                store.close()
            except Exception:
                pass


class _RaisingSource:
    size = (1600, 100)
    mode = "RGBA"

    def crop(self, box):
        raise RuntimeError("store closed mid-compute")


def test_mid_compute_read_error_aborts_all_entry_points(monkeypatch):
    import shared.analysis.diff_source as ds_mod

    good = Image.new("RGBA", (1600, 100), "green")
    for workers in (1, 2):
        monkeypatch.setattr(ds_mod, "_resolve_ssim_workers", lambda total, w=workers: w)
        assert (
            ds_mod.create_highlight_diff_from_sources(_RaisingSource(), good) is None
        )
        assert (
            ds_mod.create_grayscale_diff_from_sources(_RaisingSource(), good) is None
        )
    for workers in (1, 2):
        # Edge resolves workers through diff_source's own import binding.
        monkeypatch.setattr(ds_mod, "_resolve_edge_workers", lambda total, w=workers: w)
        assert ds_mod.create_edge_map_from_sources(_RaisingSource()) is None