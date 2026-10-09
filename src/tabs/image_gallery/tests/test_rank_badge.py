"""Shared rank-badge resolver (services/rank_badge) — single source of truth.

The grid cards, the quick-look strip and the list rows all derive their rank
badge here, so the priority rule (``crown_rank ?? rank``, leader → ``#1``,
``SOURCE``/``…``) lives in one place instead of three drifted copies.
"""

from __future__ import annotations

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
