"""Quick Look tiled path — additive regression against the cover / first-frame path.

W1 landed the tiled single-source renderer as an *additive* live surface: the
raster/cover path stays the pre-first-frame / fail-open plate, there is no
second live surface, and a new item retires the previous item's tiled source.
These tests pin that observable behavior offscreen (no RHI present), plus the
size bounds that distinguish the paths:

- the full tiled live decode applies **no** source-edge cap;
- the transient cover raster keeps its 2048 edge cap;
- the canvas-private demand pyramid keeps its 8192 edge cap;
- tiled + coarse sources coexist on one ``QuickLookCanvasWidget`` and the
  tiled source is dropped when the item changes.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.ui.quick_look import preview as _preview
from tabs.image_gallery.ui.quick_look import preview_canvas as _canvas_mod
from tabs.image_gallery.ui.quick_look import preview_canvas_host as host


def _tiny_store(w: int = 1024, h: int = 1024):
    import numpy as np
    from PIL import Image

    from engine.store.tiled_pixel_store import TiledPixelStore

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = 180
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, "RGBA"))


class _BigStore:
    """Minimal TiledPixelStore stand-in for the decode-cap probes."""

    def __init__(self, w: int, h: int) -> None:
        self.size = (w, h)
        self.is_open = True
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.is_open = False


def _patch_from_path(monkeypatch, store):
    from engine.store import tiled_pixel_store as tps

    def _fake_from_path(cls, *_a, **_k):
        return store

    monkeypatch.setattr(tps.TiledPixelStore, "from_path", _fake_from_path)


def test_caps_tiled_uncapped_cover_2048_pyramid_8192():
    # Cover / first-frame raster bounds stay where they were.
    assert _canvas_mod._DECODE_EDGE_CAP == 2048
    assert _preview._PREVIEW_FULL_DECODE_EDGE == 2048
    # Canvas-private demand pyramid bound (raised to 8192 so a large source
    # still builds an LOD pyramid, which the tiled path binds to avoid
    # mip-edge tile seams).
    assert _canvas_mod._QL_FULL_EDGE_CAP == 8192


def test_tiled_decode_is_uncapped_cover_decode_is_capped(monkeypatch):
    from engine.store import tiled_pixel_store as tps

    # A 9000px source exceeds both the 2048 cover cap and the 8192 pyramid cap.
    big = _BigStore(9000, 9000)
    _patch_from_path(monkeypatch, big)

    # The tiled live path deliberately applies no source-edge cap.
    got = host._decode_full_store_uncapped("/tmp/does-not-matter.png", None)
    assert got is big, "tiled live decode must not cap the source edge"

    # The demand-pyramid decode still caps at 8192 and closes the store.
    big2 = _BigStore(9000, 9000)
    _patch_from_path(monkeypatch, big2)
    capped = _canvas_mod._ql_decode_full_store("/tmp/does-not-matter.png", None)
    assert capped is None, "cover/pyramid decode must keep its 8192 cap"
    assert big2.closed is True, "capped store must be closed, not leaked"

    # Under the cap, the pyramid decode returns the store.
    small = _BigStore(1024, 1024)
    _patch_from_path(monkeypatch, small)
    assert _canvas_mod._ql_decode_full_store("/tmp/does-not-matter.png", None) is small


def test_tiled_path_is_additive_single_surface_and_retires_on_item_change():
    from PySide6.QtWidgets import QRhiWidget

    from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget

    app = QApplication.instance() or QApplication([])
    canvas = QuickLookCanvasWidget()
    parent = QWidget()
    canvas.setParent(parent)
    try:
        coarse = _tiny_store()
        full = _tiny_store()
        canvas.set_source(coarse)
        canvas.set_tiled_source("item-a", full)

        # Both paths coexist on the one canvas widget (no second surface: the
        # tiled renderer is a draw strategy on the same QRhiWidget, not a
        # second QRhiWidget child).
        assert canvas._store is coarse
        assert canvas._tiled_source == ("item-a", full)
        assert canvas.findChildren(QRhiWidget) == [], "tiled path must not add a second surface"

        # Changing the item retires the stale tiled source.
        coarse_b = _tiny_store()
        canvas.set_source(coarse_b)
        assert canvas._store is coarse_b
        assert canvas._tiled_source is None, "item change must drop the stale tiled source"

        # clear_tiled_source is idempotent and never raises.
        canvas.clear_tiled_source()
        canvas.clear_tiled_source()
        assert canvas._tiled_source is None
    finally:
        try:
            canvas.release_resources()
        except Exception:
            pass
        canvas.setParent(None)
        parent.deleteLater()
        app.processEvents()


def test_raster_frame_reuses_last_good_frame_on_miss():
    """Zoom/decode miss must reuse the last frame, never present nothing.

    After the first frame the cover is gone; if a zoom makes both the tiled
    plan (not ``covered``) and the raster (unbuilt LOD level -> ``None``) miss,
    the QRhiWidget would present no pass at all -- a see-through hole. The
    wrapper returns the cached frame instead.
    """
    from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget

    app = QApplication.instance() or QApplication([])
    canvas = QuickLookCanvasWidget()
    parent = QWidget()
    canvas.setParent(parent)
    try:
        good = (2, 2, b"\x10" * 16)
        calls = {"n": 0}

        def fake_compute(_target):
            calls["n"] += 1
            if calls["n"] == 1:
                canvas._frame_bytes = good  # real compute caches on success
                return good
            return None  # unbuilt level / empty composition

        canvas._compute_raster_frame = fake_compute
        assert canvas._raster_frame(None) == good
        assert canvas._raster_frame(None) == good, "miss must reuse the last frame"
        assert calls["n"] == 2
        # Before any good frame the cover still owns the pane -> None is fine.
        canvas._frame_bytes = None
        assert canvas._raster_frame(None) is None
    finally:
        canvas.setParent(None)
        parent.deleteLater()
        app.processEvents()


def test_partial_coverage_keeps_raster_takeover_only_when_covered():
    """Handover fix: takeover keys off ``TiledViewResult.covered``.

    A drawn-but-not-covered frame must NOT take over (the raster/cover plate
    stays), and ``_settle_present`` must fire at most once, on the covered
    frame. The engine view submits the partial frame's uploads internally, so
    progress continues while the plate stays up.
    """
    from engine.gpu.tiled_image_view import TiledViewResult

    from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget

    app = QApplication.instance() or QApplication([])
    canvas = QuickLookCanvasWidget()
    parent = QWidget()
    canvas.setParent(parent)
    try:
        partial = TiledViewResult(drawn=True, covered=False, instances=1, resident=1)
        covered = TiledViewResult(drawn=True, covered=True, instances=4, resident=4)

        class _FakeView:
            def __init__(self):
                self.results = [partial, covered]
                self.calls = 0

            def has_source(self):
                return True

            def render(self, *_a, **_k):
                self.calls += 1
                return self.results.pop(0)

        fake = _FakeView()
        canvas._tile_renderer = fake
        canvas._tiled_source = ("item", object())
        canvas._tile_level_ready = True  # multi-level binding -> covered is seam-safe
        canvas._ensure_tile_renderer = lambda: fake
        settled: list = []
        canvas._settle_present = lambda: settled.append(1)

        assert canvas._render_tiled(object(), object(), None, None, 100, 100) is False
        assert fake.calls == 1
        assert settled == [], "partial coverage must not take over or settle"

        assert canvas._render_tiled(object(), object(), None, None, 100, 100) is True
        assert fake.calls == 2
        assert settled == [1], "covered handover settles exactly once"
    finally:
        canvas.setParent(None)
        parent.deleteLater()
        app.processEvents()


def test_covered_but_level_not_ready_holds_raster():
    """Takeover is held until a genuine multi-level (pyramid) binding exists.

    A covered frame from a single-level binding (no pyramid, or only level 0
    built) would flash the mip-edge seam grid when the full-res store is shown
    downscaled; the raster (coarse, seam-free) must stay until the view holds
    >= 2 registered levels, at which point its own LOD/``covered`` is the
    seam-safe handover gate. The old QL-side level rebind is gone; the flag
    ``_tile_level_ready`` records that binding state.
    """
    from engine.gpu.tiled_image_view import TiledViewResult

    from tabs.image_gallery.ui.quick_look.preview_canvas import QuickLookCanvasWidget

    app = QApplication.instance() or QApplication([])
    canvas = QuickLookCanvasWidget()
    parent = QWidget()
    canvas.setParent(parent)
    try:
        covered = TiledViewResult(drawn=True, covered=True, instances=4, resident=4)

        class _FakeView:
            def has_source(self):
                return True

            def render(self, *_a, **_k):
                return covered

        canvas._tile_renderer = _FakeView()
        canvas._tiled_source = ("item", object())
        canvas._tile_level_ready = False  # single-level / pre-level -> hold
        canvas._ensure_tile_renderer = lambda: canvas._tile_renderer
        canvas._settle_present = lambda: (_ for _ in ()).throw(
            AssertionError("must not settle while the level is not matched")
        )
        assert canvas._render_tiled(object(), object(), None, None, 100, 100) is False
    finally:
        canvas.setParent(None)
        parent.deleteLater()
        app.processEvents()
