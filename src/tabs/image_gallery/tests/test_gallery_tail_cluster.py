"""Append regroup: new files form NEW series from the UNGROUPED tail.

Attach-only appends never compare new files with each other, so two
mutually-similar drops in a row would sit UNGROUPED until a manual
re-cluster. After ``_attach_append_items`` the controller regroups the
tail (old singletons + fresh misses, pins excluded) via ``cluster_items``;
groups >=2 join ``state.series`` with continuing stable ids.

Also pinned: signatures come from the perceptual cache — appending 1 file
to a tail of N decodes exactly 1 file, never N+1.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThreadPool

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Mode, Series, TriageState


def _vsplit(path: Path, left: tuple, right: tuple, w: int = 64, h: int = 64) -> Path:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = left if x < w // 2 else right
    im.save(path)
    return path


def _hsplit(path: Path, top: tuple, bottom: tuple, w: int = 64, h: int = 64) -> Path:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = top if y < h // 2 else bottom
    im.save(path)
    return path


def _diag(path: Path, c1: tuple, c2: tuple, w: int = 64, h: int = 64) -> Path:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = c1 if x > y else c2
    im.save(path)
    return path


def _item(path: Path) -> GalleryItem:
    return GalleryItem(path=path, mtime_ns=path.stat().st_mtime_ns)


from tabs.image_gallery.tests.test_triage_view_stability import _ScanStub


class _StubWidget(_ScanStub):
    """Record stub: _ScanStub plus triage delivery capture."""

    def __init__(self) -> None:
        super().__init__()
        self.triage_calls: list = []

    def set_triage(self, series, mode, source) -> None:
        self.triage_calls.append((list(series), mode, source))
        super().set_triage(series, mode, source)


def _make_ctrl(widget):
    from tabs.image_gallery.tests._gallery_dispatch_doubles import make_gallery_context

    context, _store = make_gallery_context()
    ctrl = GalleryController(widget, thread_pool=QThreadPool.globalInstance(), context=context)
    ctrl._load_thumbnail = lambda item: None  # type: ignore[method-assign]
    return ctrl


def _grouped_ctrl(tmp_path: Path):
    """Controller with a quiet grouped pool: blue pair = one live series.

    Mirrors production numbering: the seed run issues stable ids from the
    shared counter (fresh worlds start at series_2 — the counter
    pre-increments), so the fixture carries next_id=2 like a real pool.
    """
    widget = _StubWidget()
    ctrl = _make_ctrl(widget)
    blue_a = _hsplit(tmp_path / "blue_a.png", (30, 30, 180), (230, 230, 230))
    blue_b = _hsplit(tmp_path / "blue_b.png", (30, 30, 180), (230, 230, 230))
    b1, b2 = _item(blue_a), _item(blue_b)
    b1.series_id, b1.rank = "series_2", 1
    b2.series_id, b2.rank = "series_2", 2
    ctrl.state = GalleryState(folder=tmp_path, items=[b1, b2], triage_state=TriageState.DONE)
    ctrl.state.series = [Series(id="series_2", members=[b1, b2])]
    ctrl._series_next_id = 2
    return ctrl, widget, (b1, b2)


def _members(entry) -> list:
    if hasattr(entry, "members"):
        return list(entry.members or [])
    return list(entry)


def test_append_forms_new_series_from_mutual_similars(tmp_path) -> None:
    """Two mutually-similar drops join a NEW series, existing one untouched."""
    ctrl, widget, (b1, b2) = _grouped_ctrl(tmp_path)
    red_a = _vsplit(tmp_path / "red_a.png", (180, 30, 30), (10, 10, 10))
    red_b = _vsplit(tmp_path / "red_b.png", (180, 30, 30), (10, 10, 10))
    ctrl.open_paths([red_a, red_b])
    assert [s.id for s in ctrl.state.series] == ["series_2", "series_3"]
    assert _members(ctrl.state.series[0]) == [b1, b2]
    new_members = _members(ctrl.state.series[1])
    assert sorted(str(m.path) for m in new_members) == sorted([str(red_a), str(red_b)])
    assert ctrl._series_next_id == 3
    # The grouped view was delivered (no cover, no teardown path).
    assert widget.triage_calls, "expected set_triage delivery"
    delivered = widget.triage_calls[-1][0]
    assert [s.id for s in delivered] == ["series_2", "series_3"]


def test_attach_miss_without_partner_stays_ungrouped(tmp_path) -> None:
    """A lone dissimilar drop misses attach AND forms no series."""
    ctrl, _widget, _blues = _grouped_ctrl(tmp_path)
    loner = _diag(tmp_path / "loner.png", (200, 200, 30), (30, 200, 200))
    ctrl.open_paths([loner])
    assert [s.id for s in ctrl.state.series] == ["series_2"]
    lone = next(it for it in ctrl.state.items if it.path == loner)
    assert lone.series_id is None


def test_old_singleton_groups_with_new_arrival(tmp_path) -> None:
    """A previous miss completes a pair with the new drop (old tail counts)."""
    ctrl, _widget, _blues = _grouped_ctrl(tmp_path)
    loner = _diag(tmp_path / "loner.png", (200, 200, 30), (30, 200, 200))
    ctrl.open_paths([loner])
    assert [s.id for s in ctrl.state.series] == ["series_2"]
    loner2 = _diag(tmp_path / "loner2.png", (200, 200, 30), (30, 200, 200))
    ctrl.open_paths([loner2])
    assert [s.id for s in ctrl.state.series] == ["series_2", "series_3"]
    new_members = _members(ctrl.state.series[1])
    assert sorted(str(m.path) for m in new_members) == sorted([str(loner), str(loner2)])


def test_tail_cluster_uses_cached_signatures(tmp_path, monkeypatch) -> None:
    """Appending 1 file to a tail decodes exactly 1 file (cache, not N+1)."""
    from tabs.image_gallery.services import clustering as _clustering

    _clustering.clear_signature_cache()
    ctrl, _widget, _blues = _grouped_ctrl(tmp_path)
    red_a = _vsplit(tmp_path / "red_a.png", (180, 30, 30), (10, 10, 10))
    ctrl.open_paths([red_a])  # primes the cache: blues + red_a decoded once
    decoded: list[str] = []
    _orig_phash = _clustering.compute_phash
    _orig_embed = _clustering.embedding

    def _count_phash(path):
        decoded.append(f"phash:{path}")
        return _orig_phash(path)

    def _count_embed(path):
        decoded.append(f"embed:{path}")
        return _orig_embed(path)

    monkeypatch.setattr(_clustering, "compute_phash", _count_phash)
    monkeypatch.setattr(_clustering, "embedding", _count_embed)
    red_b = _vsplit(tmp_path / "red_b.png", (180, 30, 30), (10, 10, 10))
    ctrl.open_paths([red_b])
    # Only the genuinely-new file decoded; the cached tail never re-read.
    assert sorted(decoded) == sorted([f"phash:{red_b}", f"embed:{red_b}"])
    assert [s.id for s in ctrl.state.series] == ["series_2", "series_3"]


def test_append_starts_stage2_analysis_for_new_items(tmp_path, monkeypatch) -> None:
    """Appended items get Stage-2 analyses (artifacts/fidelity/camera).

    Regression: the quiet-append attach path attached the card but never
    called ``_start_proxy_analysis``, so a file dropped after the first
    series showed "not measured" rows while the first-drop cards were fully
    analyzed.
    """
    ctrl, _widget, _blues = _grouped_ctrl(tmp_path)
    ctrl.state.mode = Mode.CAMERA
    ctrl.state.source_path = None
    calls: list = []
    monkeypatch.setattr(
        ctrl,
        "_start_proxy_analysis",
        lambda items, src, mode, **kw: calls.append((list(items), src, mode)),
    )
    new = _vsplit(tmp_path / "new.png", (180, 30, 30), (10, 10, 10))
    ctrl.open_paths([new])
    assert calls, "expected a Stage-2 analysis start on append"
    items, src, mode = calls[-1]
    assert [str(it.path) for it in items] == [str(new)]
    assert src is None
    assert mode == Mode.CAMERA


def test_huge_tail_skips_quadratic_pass(tmp_path) -> None:
    """Past the tail limit no regroup runs (no crash, no I/O, no groups)."""
    from tabs.image_gallery.controller import _TAIL_CLUSTER_LIMIT

    widget = _StubWidget()
    ctrl = _make_ctrl(widget)
    fakes = [GalleryItem(path=Path(f"/none/{i}.png"), mtime_ns=i) for i in range(_TAIL_CLUSTER_LIMIT + 1)]
    ctrl.state = GalleryState(folder=tmp_path, items=list(fakes), triage_state=TriageState.DONE)
    ctrl.state.series = []
    assert ctrl._cluster_tail_into_series() == []
    assert ctrl.state.series == []
