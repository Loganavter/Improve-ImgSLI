"""Wave S1 — stable series ids + pure regroup + attach.

Pure translation/regroup/attach behavior. Offscreen-safe, no
``QDrag.exec`` anywhere (no QtDnD at all — plain function calls).

Covers the frozen S1/S2 seam:

* ``translate_computed_to_stable``: same computed input twice → same
  stable ids; counter monotonic, never reused;
* ``regroup_items``: 0-close (1-member manual sections STAY visible,
  emptied groups close, UNGROUPED-forced stays out), stable ids kept;
* ``attach_items`` / ``series_centroids`` / ``nearest_series_id``:
  near-centroid attaches, far → None, existing membership untouched.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import GalleryItem, Series
from tabs.image_gallery.services import clustering as cl
from tabs.image_gallery.use_cases import series_override as ov


def _item(name: str) -> GalleryItem:
    return GalleryItem(path=Path(f"/fake/stable/{name}"), mtime_ns=0)


def _painted(tmp_path: Path, name: str, kind: str) -> Path:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(im)
    if kind == "circle":
        d.ellipse([16, 16, 48, 48], fill="red")
    else:
        d.rectangle([8, 8, 40, 40], fill="blue")
    p = tmp_path / name
    im.save(p)
    return p


def _real_item(p: Path) -> GalleryItem:
    return GalleryItem(path=p, mtime_ns=p.stat().st_mtime_ns)


# -- translation -------------------------------------------------------------


def _computed_world():
    a1, a2 = _item("a1.png"), _item("a2.png")
    b1, b2 = _item("b1.png"), _item("b2.png")
    for m in (a1, a2):
        m.series_id = "series_1"
    for m in (b1, b2):
        m.series_id = "series_2"
    computed = [
        Series(id="series_1", members=[a1, a2], centroid=[0.1, 0.2], phash_centroid=7),
        Series(id="series_2", members=[b1, b2], centroid=[0.9, 0.8], phash_centroid=9),
    ]
    return computed, [a1, a2, b1, b2]


def test_translate_same_input_twice_same_stable_ids():
    computed, items = _computed_world()
    stable1, next1 = ov.translate_computed_to_stable(computed, 0)
    # Same computed input, same counter → same stable ids.
    stable2, next2 = ov.translate_computed_to_stable(computed, 0)
    assert [s.id for s in stable1] == [s.id for s in stable2]
    assert next1 == next2 == 2
    assert [s.id for s in stable1] == ["series_1", "series_2"]
    # Members now carry the stable ids; seed ids never stored or shown.
    assert {m.series_id for m in items} == {"series_1", "series_2"}


def test_translate_counter_monotonic_never_reused():
    computed, _ = _computed_world()
    _, next1 = ov.translate_computed_to_stable(computed, 0)
    c1, c2 = _item("c1.png"), _item("c2.png")
    for m in (c1, c2):
        m.series_id = "series_1"  # seed id, colliding on purpose
    later = [Series(id="series_1", members=[c1, c2], centroid=[0.5, 0.5])]
    stable, next2 = ov.translate_computed_to_stable(later, next1)
    assert [s.id for s in stable] == ["series_3"]
    assert next2 == 3
    assert c1.series_id == "series_3" == c2.series_id


# -- regroup (0-close) -------------------------------------------------------


def _stable_world():
    a1, a2 = _item("a1.png"), _item("a2.png")
    b1, b2 = _item("b1.png"), _item("b2.png")
    a1.series_id, a1.rank = "series_1", 1
    a2.series_id, a2.rank = "series_1", 2
    b1.series_id, b1.rank = "series_2", 1
    b2.series_id, b2.rank = "series_2", 2
    last = [
        Series(id="series_1", members=[a1, a2], centroid=[0.1, 0.2]),
        Series(id="series_2", members=[b1, b2], centroid=[0.9, 0.8]),
    ]
    return [a1, a2, b1, b2], last


def test_regroup_move_keeps_both_ids_no_dissolve():
    items, last = _stable_world()
    a1, a2, b1, b2 = items
    overrides = {str(a2.path): "series_2"}
    out = ov.regroup_items(items, overrides, last)
    by_id = {s.id: list(s.members) for s in out}
    assert set(by_id) == {"series_1", "series_2"}
    # Host keeps its id with 3 members; donor keeps its id with 1 member.
    assert {m.path.name for m in by_id["series_2"]} == {"a2.png", "b1.png", "b2.png"}
    assert [m.path.name for m in by_id["series_1"]] == ["a1.png"]
    assert a1.series_id == "series_1" and a1.rank == 1  # survivor, positional
    assert a2.series_id == "series_2"


def test_regroup_emptied_group_closes():
    items, last = _stable_world()
    a1, a2, b1, b2 = items
    overrides = {str(a1.path): "series_2", str(a2.path): "series_2"}
    out = ov.regroup_items(items, overrides, last)
    assert [s.id for s in out] == ["series_2"]
    assert {m.path.name for m in out[0].members} == {"a1.png", "a2.png", "b1.png", "b2.png"}


def test_regroup_ungrouped_forced_stays_out():
    items, last = _stable_world()
    a1, a2, b1, b2 = items
    overrides = {str(b2.path): None}
    out = ov.regroup_items(items, overrides, last)
    assert b2.series_id is None and b2.rank is None
    host = [s for s in out if s.id == "series_2"]
    assert len(host) == 1 and [m.path.name for m in host[0].members] == ["b1.png"]
    # Untouched group reused verbatim (no churn).
    kept = [s for s in out if s.id == "series_1"]
    assert len(kept) == 1 and kept[0] is last[0]


# -- attach ------------------------------------------------------------------


def _attach_world():
    m1, m2 = _item("m1.png"), _item("m2.png")
    m1.series_id, m1.rank = "series_1", 1
    m2.series_id, m2.rank = "series_1", 2
    n1 = _item("n1.png")
    n1.series_id, n1.rank = "series_2", 1
    existing = [
        Series(id="series_1", members=[m1, m2], centroid=[0.0, 0.0]),
        Series(id="series_2", members=[n1], centroid=[10.0, 0.0]),
    ]
    return existing, [m1, m2, n1]


def test_attach_near_centroid_far_none_membership_untouched():
    existing, members = _attach_world()
    before = {m.path.name: (m.series_id, m.rank) for m in members}
    result = ov.attach_items(
        {
            "/fake/stable/new_near.png": [0.05, 0.0],
            "/fake/stable/new_far.png": [5.0, 5.0],
        },
        existing,
    )
    assert result["/fake/stable/new_near.png"] == "series_1"
    assert result["/fake/stable/new_far.png"] is None
    # Existing membership untouched.
    assert {m.path.name: (m.series_id, m.rank) for m in members} == before


def test_attach_accepts_item_pairs_and_threshold_gate():
    existing, _ = _attach_world()
    newbie = _item("newbie.png")
    result = ov.attach_items([((newbie), [9.9, 0.0])], existing, threshold=10)
    assert result[str(newbie.path)] == "series_2"
    # Same vector, stricter hamming threshold → tighter embed gate → still
    # attached here (0.1 well inside 0.4); a mid-range vector is gated out.
    mid = ov.attach_items({"/fake/stable/mid.png": [0.45, 0.0]}, existing, threshold=5)
    assert mid["/fake/stable/mid.png"] is None


def test_series_centroids_prefers_stored_recomputes_missing(tmp_path):
    stored = Series(id="series_9", members=[_item("x.png")], centroid=[0.25, 0.5])
    p1 = _real_item(_painted(tmp_path, "r1.png", "circle"))
    p2 = _real_item(_painted(tmp_path, "r2.png", "circle"))
    bare = Series(id="series_10", members=[p1, p2], centroid=None)
    got = cl.series_centroids([stored, bare])
    assert got["series_9"] == [0.25, 0.5]
    _, e1 = cl.signature_for(p1.path)
    _, e2 = cl.signature_for(p2.path)
    expected = [(a + b) / 2 for a, b in zip(e1, e2)]
    assert len(got["series_10"]) == len(expected)
    assert all(abs(a - b) < 1e-9 for a, b in zip(got["series_10"], expected))


def test_nearest_series_id_gate_and_ties():
    centroids = {"series_1": [0.0, 0.0], "series_2": [10.0, 0.0]}
    assert cl.nearest_series_id([0.05, 0.0], centroids) == "series_1"
    assert cl.nearest_series_id([5.0, 5.0], centroids) is None
    assert cl.nearest_series_id([], centroids) is None
    # Equidistant → smallest id wins (deterministic).
    tied = {"series_2": [0.25, 0.0], "series_1": [-0.25, 0.0]}
    assert cl.nearest_series_id([0.0, 0.0], tied) == "series_1"


def test_translate_skips_pinned_ids():
    """Seed never merges a fresh auto group into a pinned manual section."""
    from tabs.image_gallery.use_cases import series_override as _ov

    a, b = _item("a.png"), _item("b.png")
    out, nxt = _ov.translate_computed_to_stable(
        [Series(id="series_9", members=[a, b])], 0, skip_ids={"series_1"}
    )
    assert [m.series_id for m in out[0].members] == ["series_2", "series_2"]
    assert out[0].id == "series_2"
    assert nxt == 2
