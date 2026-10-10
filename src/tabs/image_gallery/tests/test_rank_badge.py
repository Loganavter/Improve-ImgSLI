"""Shared rank-badge resolver (services/rank_badge) — single source of truth.

The grid cards, the quick-look strip and the list rows all derive their rank
badge here, so the priority rule (``crown_rank ?? rank``, leader → ``#1``,
``SOURCE``/``…``) lives in one place instead of three drifted copies.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.services.rank_badge import (
    KIND_NONE,
    KIND_RANK,
    KIND_SOURCE,
    resolve_rank_badge,
)


def _item(**kw):
    return SimpleNamespace(**kw)


def test_plain_is_none() -> None:
    b = resolve_rank_badge(_item())
    assert b.kind == KIND_NONE and b.text == "" and b.rank is None


def test_rank_and_crown_priority() -> None:
    assert resolve_rank_badge(_item(rank=3)).text == "#3"
    crowned = resolve_rank_badge(_item(rank=3, crown_rank=2))
    assert crowned.text == "#2" and crowned.rank == 2 and crowned.kind == KIND_RANK


def test_leader_as_rank_flag() -> None:
    # Cards/strip: a leader with no explicit rank shows #1.
    assert resolve_rank_badge(_item(is_best=True)).text == "#1"
    # List: keeps the ★ affordance, no synthetic number.
    b = resolve_rank_badge(_item(is_best=True), leader_as_rank=False)
    assert b.text == "" and b.is_best is True


def test_source_priority() -> None:
    src = resolve_rank_badge(_item(rank=3), is_source=True)
    assert src.kind == KIND_SOURCE and src.text == "SOURCE"


def test_rejected_reported_not_folded() -> None:
    # The list keeps the rank and appends ✕; the resolver never folds it in.
    b = resolve_rank_badge(_item(rank=3, rejected=True))
    assert b.rejected is True and b.text == "#3"
    b2 = resolve_rank_badge(_item(rejected=True))
    assert b2.rejected is True and b2.text == ""


def test_bad_rank_never_raises() -> None:
    b = resolve_rank_badge(_item(rank="oops"))
    assert b.text == "" and b.rank is None


def test_stamp_badges_sets_source_and_rank() -> None:
    """One computation stamps every item's display badge + kind."""
    from tabs.image_gallery.services.rank_badge import stamp_badges

    src = _item(path="/gallery/src.png", rank=1)
    other = _item(path="/gallery/o.png", rank=2)
    stamp_badges([src, other], "/gallery/src.png")
    assert (src.badge, src.badge_kind) == ("SOURCE", KIND_SOURCE)
    assert (other.badge, other.badge_kind) == ("#2", KIND_RANK)


def test_stamp_badges_leader_and_rejected() -> None:
    from tabs.image_gallery.services.rank_badge import stamp_badges

    leader = _item(path="/gallery/l.png", is_best=True)
    rej = _item(path="/gallery/r.png", rejected=True)
    stamp_badges([leader, rej], None)
    assert (leader.badge, leader.badge_kind) == ("#1", KIND_RANK)
    assert (rej.badge, rej.badge_kind) == ("", KIND_NONE)


def test_stamp_badges_source_path_none_never_marks_source() -> None:
    from tabs.image_gallery.services.rank_badge import stamp_badges

    it = _item(path="/gallery/x.png", rank=1)
    stamp_badges([it], None)
    assert it.badge == "#1" and it.badge_kind == KIND_RANK


def test_sync_source_badge_moves_source_now(qtbot) -> None:
    """'Make source' moves the badge immediately, without the comparison pass.

    ``sync_source_badge`` stamps all items and repaints only the two cards
    whose badge moved (old + new source) — no decode, no fidelity worker.
    """
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    src = _item(path="/gallery/src.png", rank=1)
    other = _item(path="/gallery/o.png", rank=2)
    src.badge, src.badge_kind = "SOURCE", KIND_SOURCE
    other.badge, other.badge_kind = "#2", KIND_RANK
    w._items = [src, other]
    w._series = []
    w._source_path = "/gallery/src.png"
    repainted: list[list[str]] = []
    w.refresh_cards = lambda items: repainted.append([str(i.path) for i in items])

    w.sync_source_badge("/gallery/o.png")

    assert (other.badge, other.badge_kind) == ("SOURCE", KIND_SOURCE)
    assert (src.badge, src.badge_kind) == ("#1", KIND_RANK)
    assert w._source_path == Path("/gallery/o.png")
    assert repainted and set(repainted[0]) == {"/gallery/src.png", "/gallery/o.png"}
