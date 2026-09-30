"""Preview-first invariant: full note implies preview tier present.

``apply_full_resolution`` demand-fills the preview tier via the frozen
seam (``tabs._shared.loading_pipeline.get_or_load_preview`` — bounded,
fail-open) BEFORE ``put_pixel`` + ``note_slot_pixels("full")``. Peek
first: a same-path sibling's cached preview is never re-decoded.
Fill-miss (``None``) preserves today's behavior exactly.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QImage

from tabs.multi_compare.pipeline.cache import MultiComparePixelCache
from tabs.multi_compare.use_cases import loading as loading_use_cases


def _color_image(r=40, g=120, b=200):
    img = QImage(8, 8, QImage.Format.Format_RGBA8888)
    img.fill(QColor(r, g, b))
    assert not img.isNull()
    return img


class _FakeStore:
    def __init__(self, tag="full", *, open=True):
        self.tag = tag
        self._open = open

    def is_open(self):
        return self._open


def _write_file(path: Path, payload: bytes = b"x") -> Path:
    path.write_bytes(payload)
    return path


def _make_controller(cache, slot_id=0, path=None):
    slot = SimpleNamespace(id=slot_id, path=path)
    dispatched: list = []

    def _dispatch(action):
        dispatched.append(action)

    mc_store = SimpleNamespace(dispatch=_dispatch, dispatched=dispatched)
    widget = SimpleNamespace(
        state=SimpleNamespace(slots=[slot]),
        store=mc_store,
    )
    controller = SimpleNamespace(
        widget=widget,
        pixel_cache=cache,
    )
    return controller, dispatched


def _full_notes(dispatched):
    return [a for a in dispatched if getattr(a, "tier", None) == "full"]


def test_full_note_implies_preview_present(monkeypatch, tmp_path):
    """Full apply with an empty preview tier fills it before the note."""
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "img.png", b"payload-1")
    expected = _color_image()
    calls: list[str] = []
    monkeypatch.setattr(
        pl, "load_preview_image", lambda path: (calls.append(str(path)), expected)[1]
    )
    cache = MultiComparePixelCache()
    controller, dispatched = _make_controller(cache, slot_id=0, path=f)
    store = _FakeStore("full-0")

    loading_use_cases.apply_full_resolution(controller, 0, f, store)

    assert _full_notes(dispatched), "today's full note still dispatched"
    assert len(calls) == 1, "preview demand-filled exactly once"
    got = cache.get_preview(f)
    assert got is expected
    assert cache.get_pixel(f) is store


def test_sibling_shared_preview_not_redecoded(monkeypatch, tmp_path):
    """Same-path sibling already holds the preview: no second decode."""
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "img.png", b"payload-2")
    shared = _color_image(9, 200, 9)
    cache = MultiComparePixelCache()
    cache.put_preview(f, shared)

    def _boom(path):
        raise AssertionError("must not re-decode a cached sibling preview")

    monkeypatch.setattr(pl, "load_preview_image", _boom)
    controller, dispatched = _make_controller(cache, slot_id=1, path=f)
    store = _FakeStore("full-1")

    loading_use_cases.apply_full_resolution(controller, 1, f, store)

    assert _full_notes(dispatched), "full note still dispatched"
    assert cache.get_preview(f) is shared, "sibling preview untouched"
    assert cache.get_pixel(f) is store


def test_fill_none_still_notes_fail_open_preserved(monkeypatch, tmp_path):
    """Unreadable preview (fill returns None): store still cached + noted."""
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "img.png", b"payload-3")
    monkeypatch.setattr(pl, "load_preview_image", lambda path: None)
    cache = MultiComparePixelCache()
    controller, dispatched = _make_controller(cache, slot_id=2, path=f)
    store = _FakeStore("full-2")

    loading_use_cases.apply_full_resolution(controller, 2, f, store)

    assert _full_notes(dispatched), "fail-open: full note preserved on fill miss"
    assert cache.get_pixel(f) is store
    assert cache.get_preview(f) is None, "miss plants nothing"
