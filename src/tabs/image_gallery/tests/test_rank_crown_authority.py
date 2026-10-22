"""ONE card may wear ★ BEST — the terminal ranker owns the crown.

Owner screenshot 2026-10-22: two cards showed ★ ЛУЧШЕЕ at once (ranks #3/#2/#2/#6
around them). Two authorities can crown a card in the AI domain:

* the Stage-3 VLM tie-break — it sets ``is_best`` / ``crown_rank`` on its winner;
* the terminal Jev rank — it marks its rank-1 member ``is_best``.

``rank_badge.resolve_rank_badge`` paints BEST for every item with
``is_best=True``, so both crowns survive and two cards claim the series. P3-A
made Jev the TERMINAL calculator: when it has ranked the series, the tie-break
verdict is note-level information (hover/state), never a second crown.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services.rank_badge import resolve_rank_badge
from tabs.image_gallery.use_cases import tie_break


def _item(name: str, rank: int, *, source: str = "jev", best: bool = False) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    it.rank = rank
    it.rank_source = source
    it.is_best = best
    return it


class _Owner:
    def __init__(self, *items) -> None:
        self.state = SimpleNamespace(
            items=list(items), series=[], tie_breaks={}, rank_domain="ai"
        )
        self._judgment_domain = "ai"
        self._domain_epoch = 4
        self._folder_gen = 2
        self.refreshed: list = []
        self.widget = SimpleNamespace(
            refresh_card=lambda it: self.refreshed.append(it),
            refresh_cards=lambda its: None,
        )

    def _find_item(self, path):
        for it in self.state.items:
            if str(it.path) == str(path):
                return it
        return None


def _verdict(winner: GalleryItem, loser: GalleryItem):
    return SimpleNamespace(
        winner_path=str(winner.path),
        loser_path=str(loser.path),
        reason="stub",
        confidence=0.9,
    )


def test_a_tie_break_verdict_does_not_add_a_second_best_to_a_jev_ranked_series(qapp=None) -> None:
    # Jev owns the order: b is rank 1 (BEST), a is rank 2.
    a = _item("a.png", 2)
    b = _item("b.png", 1, best=True)
    owner = _Owner(a, b)

    # The tie-break (or any late verdict) prefers a.
    tie_break._apply_tie_break_result(owner, a, b, _verdict(a, b))

    best_cards = [
        it.path.name
        for it in (a, b)
        if resolve_rank_badge(it, domain="ai").kind == "best"
    ]
    assert best_cards == ["b.png"], f"two cards claim the series: {best_cards}"
    # The verdict is still recorded (hover/state), just not crowned.
    assert owner.state.tie_breaks, "the verdict should stay visible as information"


def test_a_tie_break_verdict_still_crowns_when_no_ranker_owns_the_series() -> None:
    """Control: on the AI domain with no Jev rank yet, the verdict may crown."""
    a = _item("a.png", 0, source="", best=False)
    b = _item("b.png", 0, source="", best=False)
    owner = _Owner(a, b)
    owner.state.rank_domain = "ai"

    tie_break._apply_tie_break_result(owner, a, b, _verdict(a, b))

    assert a.is_best is True and a.crown_rank == 1
    assert b.is_best is False and b.crown_rank == 2
