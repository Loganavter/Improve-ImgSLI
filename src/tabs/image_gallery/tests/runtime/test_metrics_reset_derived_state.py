"""Reset-metrics-cache must reset the DERIVED rank state + repaint the cards.

Owner report (2026-10-20): in the AI domain, after **Reset metrics cache** the
cards kept their coloured quality dots and the BEST pill / rank selection did
not reset. Root cause: the clear dropped the *measurements*
(``metrics``/``artifacts``/``analysis``) but not the metric-DERIVED rank state
(``rank`` / ``rank_source`` / ``crown_rank`` / ``is_best`` / badge triple), and
it never touched the per-card painted cache (``_gallery_dot_colors`` /
``_gallery_dot_infos`` / ``_gallery_badge``), which is stamped at card
build/update time — so the old colours and a stale ★ BEST survived until some
unrelated repaint (and the async re-triage then re-derived BEST from the stale
rank fields).

Falsification story — BOTH halves are RED on the pre-change tree (verified by
running this module against ``HEAD:use_cases/cache_reset.py``):

* ``test_reset_clears_metric_derived_rank_state`` — a ranked item
  (``rank=1`` / ``rank_source="fusion"`` / ``crown_rank=1`` / ``is_best=True``
  / ``badge="★ BEST"`` / ``triage_best=True``) keeps every one of those fields
  after ``clear_metrics_caches`` pre-change; only ``metrics`` is emptied.
* ``test_reset_repaints_card_dots_and_badge`` — a real card built for an item
  with metrics paints non-neutral dots and the ★ BEST pill; the pre-change
  reset mutates the item but never refreshes the card, so the card keeps its
  stamped coloured dots and ``_gallery_badge == "★ BEST"`` after the reset.

Product DECISION encoded here: a metrics reset is a *reset*, so an automatic
(fusion/jev) rank AND a manual ("Make best") pick both go; ``series_id`` /
``provenance_series_id`` / ``rejected`` / ``triage_rejected`` are not
metric-derived and survive.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.tests._activity_fixtures import mark_analyzing
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import ai_cache, profile_cache
from tabs.image_gallery.services.rank_badge import BEST_TEXT, KIND_BEST, KIND_NONE


@pytest.fixture
def caches(tmp_path, monkeypatch):
    """Redirect the AI scorecard dir + the profile pin cache away from $HOME."""
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: ai_dir)
    pins = tmp_path / "pins"
    pins.mkdir()
    monkeypatch.setattr(profile_cache, "_default_cache", profile_cache.ProfileCache(pins))
    return ai_dir, pins


def _ranked_item(path: Path) -> GalleryItem:
    """A measured + ranked winner (auto fusion rank + the manual pick flag)."""
    item = GalleryItem(path=path, mtime_ns=1)
    item.metrics = {"sharpness": 320.0, "noise": 0.9}
    item.rank = 1
    item.rank_source = "fusion"
    item.crown_rank = 1
    item.is_best = True
    item.badge = BEST_TEXT
    item.badge_kind = KIND_BEST
    item.badge_source = "fusion"
    # The "Make best" pick marker: not metric-derived in type, but it IS a
    # rank over the old measurements — left set it would be re-frozen as a
    # manual rank on the next snapshot and silently undo the reset.
    item.triage_best = True
    item.triage_rank = 1
    # NOT metric-derived: group identity + the user's triage decisions.
    item.series_id = "series_1"
    item.provenance_series_id = "series_1"
    item.rejected = True
    item.triage_rejected = True
    return item


def _owner(items, folder, **extra) -> SimpleNamespace:
    """The supervisor repro's owner shape (+ the live view for the repaint)."""
    return SimpleNamespace(
        state=SimpleNamespace(items=list(items), folder=Path(folder)),
        clear_metric_profile=lambda: None,
        _last_analysis_fingerprint="fp",
        **extra,
    )


def test_reset_clears_metric_derived_rank_state(tmp_path, caches) -> None:
    """Every metric-derived rank field is cleared; triage identity survives."""
    from tabs.image_gallery.use_cases import cache_reset

    item = _ranked_item(tmp_path / "a.png")
    owner = _owner([item], tmp_path)

    summary = cache_reset.clear_metrics_caches(owner)

    assert summary["items"] == 1
    # Measurements gone (the pre-existing contract).
    assert item.metrics == {}
    # Derived rank state gone — this is the half that failed pre-change.
    assert item.rank is None
    assert item.rank_source is None
    assert item.crown_rank is None
    assert item.is_best is False
    assert item.badge == ""
    assert item.badge_kind == KIND_NONE
    assert item.badge_source in ("", None)
    # A manual "Make best" pick is a rank over the old metrics: it goes too.
    assert item.triage_best is False
    assert item.triage_rank is None
    # Not metric-derived: group identity + user triage decisions survive.
    assert item.series_id == "series_1"
    assert item.provenance_series_id == "series_1"
    assert item.rejected is True
    assert item.triage_rejected is True


def test_reset_repaints_card_dots_and_badge(tmp_path, caches, qapp) -> None:
    """The bound card is re-stamped unranked and repainted by the reset itself."""
    from tabs.image_gallery.ui.card import build_gallery_card
    from tabs.image_gallery.ui.grid_view import GalleryGridView
    from tabs.image_gallery.use_cases import cache_reset

    item = _ranked_item(tmp_path / "a.png")
    # Rejected cards deliberately suppress the corner badge (dim + strike is
    # the rejected signal), so this half needs an accepted card.
    item.rejected = False
    item.triage_rejected = False
    card = build_gallery_card(item, parent=None, mode="camera")
    try:
        # Pre-state: measured dots (255-alpha severity colours among the muted
        # unscored ones) + the ★ BEST pill stamped on the card.
        assert any(c.alpha() != 120 for c in card._gallery_dot_colors)
        assert any(score is not None for _label, score in card._gallery_dot_infos)
        assert card._gallery_badge == BEST_TEXT

        view = GalleryGridView()
        try:
            view._cards_by_path[str(item.path)] = card
            owner = _owner([item], tmp_path, widget=view)

            cache_reset.clear_metrics_caches(owner)

            dots = tuple(card._gallery_dot_colors)
            # A cleared, idle card has NOTHING measured and nothing running, so
            # it paints no dots (placeholder dots are an in-progress affordance
            # since 2026-10-22 — they must not outlive the analysis).
            assert not dots
            assert not card._gallery_dot_infos
            assert not card._gallery_badge
        finally:
            view.deleteLater()
    finally:
        card.deleteLater()
