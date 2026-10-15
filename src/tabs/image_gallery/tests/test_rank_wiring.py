"""R2 — Algorithms rank wired to the measured metric fusion.

The gallery's per-series rank is the deterministic fusion of the measured
quality axes (``services.rank_fusion``), assigned by the controller, never the
old HSV-centroid order. ``rank_source`` records who produced the number:
``"fusion"`` (automatic) or ``"manual"`` (explicit Keep/Make best).

Falsification story (what each test would catch):

- a rank that still follows ``embedding_dist_to_centroid`` (the removed centroid
  order) — the ssim-swap test flips the order purely from a measured axis;
- a rank that reacts to the centroid metric at all — changing ONLY
  ``embedding_dist_to_centroid`` must move nothing;
- arrival / member-list order leaking into the rank — a reshuffled regroup with
  identical metrics must yield identical ranks;
- a manual pick silently re-derived by the next automatic regroup — Keep/Make
  best must set ``rank_source="manual"`` and survive.

No Qt event loop, no torch/PIL: a lightweight fake controller calls the real
(unbound) controller rank primitives over plain ``GalleryItem`` objects.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Mode, Series

CENTROID_KEY = "embedding_dist_to_centroid"


class _FakeController:
    """Minimal controller surface for the rank primitives (no Qt).

    ``_commit_triage_series`` converges the worker + inline paths; it needs only
    ``state``, ``_series_overrides`` and the singleton-restore tail, which is a
    no-op here (fresh worlds carry no leftovers).
    """

    def __init__(self, items, series, mode=Mode.FIDELITY) -> None:
        self.state = GalleryState(
            items=list(items), series=list(series), mode=mode
        )
        self._series_overrides: dict = {}

    # -- bound delegations to the real controller primitives ----------------
    def _apply_fusion_ranks(self, series, *, mode=None):
        return GalleryController._apply_fusion_ranks(self, series, mode=mode)

    def _mark_rank_manual(self, items):
        return GalleryController._mark_rank_manual(self, items)

    def _mark_triage_picks_manual(self):
        return GalleryController._mark_triage_picks_manual(self)

    def _emit_gallery(self, action):
        return GalleryController._emit_gallery(self, action)

    def _gallery_store(self):
        return None

    def _item_for_path(self, path):
        return GalleryController._item_for_path(self, path)

    def make_best(self, path):
        return GalleryController.make_best(self, path)

    def keep_best_of_series(self):
        return GalleryController.keep_best_of_series(self)

    # -- stubs for the shared delivery tail ---------------------------------
    def _restore_singletons(self, items, overrides, pre_ids, last_series, regrouped):
        return list(regrouped)

    def _emit_triage_finished(self, *args, **kwargs):
        return True


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _series(*items) -> list[Series]:
    return [Series(id="series_1", members=list(items))]


def _auto_rank(ctrl, series) -> None:
    """Assign the automatic rank the way an automatic triage delivery does."""
    GalleryController._commit_triage_series(ctrl, series, None, ctrl.state.mode)


# --------------------------------------------------------------------------
# rank derives from the measured axes (ssim swap flips the order)
# --------------------------------------------------------------------------


def test_ssim_swap_flips_the_order() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)

    assert (a.rank, b.rank) == (1, 2)

    # Swap ONLY the measured ssim values → the order flips.
    a.metrics["ssim"], b.metrics["ssim"] = 0.50, 0.90
    _auto_rank(ctrl, ctrl.state.series)
    assert (b.rank, a.rank) == (1, 2)


def test_rank_is_fusion_sourced_after_an_automatic_pass() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)
    assert a.rank_source == "fusion"
    assert b.rank_source == "fusion"


# --------------------------------------------------------------------------
# the centroid metric can never move a rank (RANK_EXCLUDED_AXES proof)
# --------------------------------------------------------------------------


def test_embedding_dist_to_centroid_cannot_move_any_rank() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10, **{CENTROID_KEY: 0.99})
    b = _item("b.png", ssim=0.50, noise=0.10, **{CENTROID_KEY: 0.01})
    c = _item("c.png", ssim=0.70, noise=0.10, **{CENTROID_KEY: 0.50})
    ctrl = _FakeController([a, b, c], _series(a, b, c))
    _auto_rank(ctrl, ctrl.state.series)
    before = {it.path.name: it.rank for it in (a, b, c)}
    # The best item has the *worst* centroid distance; if it counted, `b` wins.
    assert before == {"a.png": 1, "c.png": 2, "b.png": 3}

    # Rewrite ONLY the centroid metric (extreme, inverted) → no rank moves.
    a.metrics[CENTROID_KEY] = 100.0
    b.metrics[CENTROID_KEY] = -5.0
    c.metrics[CENTROID_KEY] = 42.0
    _auto_rank(ctrl, ctrl.state.series)
    assert {it.path.name: it.rank for it in (a, b, c)} == before


def test_centroid_only_items_tie_break_by_path_not_distance() -> None:
    # Two unmeasured items differing only in centroid distance: the fusion
    # order is by path (deterministic), never by the centroid.
    a = _item("a.png", **{CENTROID_KEY: 9.0})
    b = _item("b.png", **{CENTROID_KEY: 0.0})
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)
    assert (a.rank, b.rank) == (1, 2)


# --------------------------------------------------------------------------
# determinism: a regroup with unchanged metrics yields identical ranks
# --------------------------------------------------------------------------


def test_regroup_with_unchanged_metrics_keeps_ranks() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.60, noise=0.10)
    c = _item("c.png", ssim=0.30, noise=0.10)
    ctrl = _FakeController([a, b, c], _series(a, b, c))
    _auto_rank(ctrl, ctrl.state.series)
    first = {it.path.name: it.rank for it in (a, b, c)}
    assert first == {"a.png": 1, "b.png": 2, "c.png": 3}

    # Regroup: fresh Series wrapping the same items, member order shuffled.
    rng = random.Random(20261015)
    shuffled = [a, b, c]
    rng.shuffle(shuffled)
    ctrl.state.series = _series(*shuffled)
    _auto_rank(ctrl, ctrl.state.series)
    assert {it.path.name: it.rank for it in (a, b, c)} == first


# --------------------------------------------------------------------------
# Keep / Make best are manual and survive an automatic regroup
# --------------------------------------------------------------------------


def test_make_best_marks_manual_and_survives_regroup() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)
    assert a.rank == 1 and a.rank_source == "fusion"

    # User picks the fusion loser: the explicit decision wins.
    assert ctrl.make_best(b.path) is True
    assert b.rank == 1
    assert b.rank_source == "manual"

    # A later automatic regroup must NOT silently re-derive the manual pick.
    _auto_rank(ctrl, ctrl.state.series)
    assert b.rank == 1
    assert b.rank_source == "manual"


def test_keep_best_of_series_marks_manual() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)

    ctrl.keep_best_of_series()
    winner = next(it for it in (a, b) if it.is_best)
    assert winner.rank == 1
    assert winner.rank_source == "manual"
    # The keeper stays on top through another automatic pass.
    _auto_rank(ctrl, ctrl.state.series)
    assert winner.rank == 1 and winner.rank_source == "manual"


def test_non_manual_members_stay_fusion_sourced() -> None:
    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    c = _item("c.png", ssim=0.30, noise=0.10)
    ctrl = _FakeController([a, b, c], _series(a, b, c))
    _auto_rank(ctrl, ctrl.state.series)
    assert ctrl.make_best(c.path) is True
    # `c` is the manual winner; the untouched members keep a fusion source.
    assert c.rank_source == "manual"
    assert a.rank_source == "fusion"
    assert b.rank_source == "fusion"
    # Manual rank 1 wins the top slot; the others fill 2..N deterministically.
    assert c.rank == 1
    assert sorted((a.rank, b.rank)) == [2, 3]


# --------------------------------------------------------------------------
# production seam: the UI reaches the triage helpers directly, not the wrappers
# --------------------------------------------------------------------------


def test_direct_triage_pick_is_frozen_as_manual() -> None:
    from tabs.image_gallery.use_cases import triage as _triage

    a = _item("a.png", ssim=0.90, noise=0.10)
    b = _item("b.png", ssim=0.50, noise=0.10)
    ctrl = _FakeController([a, b], _series(a, b))
    _auto_rank(ctrl, ctrl.state.series)

    # The real UI path calls the triage helper with the controller as owner.
    assert _triage.make_best(ctrl, b.path) is True
    assert b.rank == 1
    assert b.rank_source == "manual"

    # And it survives the next automatic regroup.
    _auto_rank(ctrl, ctrl.state.series)
    assert b.rank == 1 and b.rank_source == "manual"
