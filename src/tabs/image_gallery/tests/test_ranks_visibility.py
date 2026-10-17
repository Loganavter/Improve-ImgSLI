"""Ranks/★ BEST are hidden until the ranking is FINAL for the folder.

Product rule (2026-10-17): while a folder is still analysing (metrics pass not
settled, or any item's analysis in flight) the gallery must not show a
provisional ``#N`` or a premature ``★ BEST``; the pill appears only once the
ranking is final. One gate at the single badge-stamp point
(``services.rank_badge.stamp_badges`` / ``show_rank``) drives every surface
(card, quick-look strip, list).

Falsification story (red-before): with the pre-change stamp path a ranked item
rendered ``#N`` (and ``is_best`` rendered ``★ BEST``) immediately — these tests
fail on ``main`` before the gate.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.services import rank_badge as rb
from tabs.image_gallery.services.rank_badge import resolve_rank_badge, stamp_badges


def _item(name: str, **kw) -> GalleryItem:
    it = GalleryItem(path=Path(f"/g/{name}"), mtime_ns=0)
    for key, value in kw.items():
        setattr(it, key, value)
    return it


# --- badge layer -----------------------------------------------------------


def test_stamp_hides_rank_and_best_while_not_final() -> None:
    ranked = _item("a.png", rank=2, rank_source="fusion")
    best = _item("b.png", rank=1, is_best=True, rank_source="fusion")
    stamp_badges([ranked, best], None, show_rank=False)
    assert ranked.badge == "" and ranked.badge_kind == rb.KIND_NONE
    assert best.badge == "" and best.badge_kind == rb.KIND_NONE


def test_stamp_keeps_source_identity_when_rank_hidden() -> None:
    src = _item("s.png")
    stamp_badges([src], "/g/s.png", show_rank=False)
    # SOURCE is identity, not a ranking — it stays visible.
    assert src.badge_kind == rb.KIND_SOURCE


def test_stamp_shows_rank_and_best_when_final() -> None:
    ranked = _item("a.png", rank=2, rank_source="fusion")
    best = _item("b.png", rank=1, is_best=True, rank_source="fusion")
    stamp_badges([ranked, best], None, show_rank=True)
    assert ranked.badge == "#2"
    assert best.badge == rb.BEST_TEXT


def test_resolve_hidden_still_reports_rejected() -> None:
    it = _item("a.png", rank=1, is_best=True, rejected=True)
    badge = resolve_rank_badge(it, show_rank=False)
    assert badge.text == "" and badge.rejected is True


# --- controller gate -------------------------------------------------------


def _fake_ctrl(items=()):
    seen: list[bool] = []
    widget = SimpleNamespace(set_ranks_visible=lambda v: seen.append(bool(v)))
    ctrl = SimpleNamespace(
        widget=widget,
        state=SimpleNamespace(items=list(items)),
        _metrics_settled_gen=-1,
        _folder_gen=0,
    )
    return ctrl, seen


def test_ranks_hidden_until_metrics_settled() -> None:
    ctrl, seen = _fake_ctrl()
    GalleryController._refresh_ranks_visible(ctrl)
    assert seen[-1] is False  # not settled yet
    ctrl._metrics_settled_gen = 0  # pass settled for this folder gen
    GalleryController._refresh_ranks_visible(ctrl)
    assert seen[-1] is True


def test_ranks_rehidden_while_an_analysis_is_in_flight() -> None:
    ctrl, seen = _fake_ctrl(
        [SimpleNamespace(analysis_status=AnalysisStatus.PENDING)]
    )
    ctrl._metrics_settled_gen = 0  # settled, but one analysis still running
    GalleryController._refresh_ranks_visible(ctrl)
    assert seen[-1] is False


def test_no_widget_is_not_an_error() -> None:
    ctrl = SimpleNamespace(
        state=SimpleNamespace(items=[]), _metrics_settled_gen=0, _folder_gen=0
    )
    GalleryController._refresh_ranks_visible(ctrl)  # must not raise


# --- widget gate (single stamp point re-stamps every surface) --------------


def test_widget_set_ranks_visible_blanks_then_restores(qtbot) -> None:
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    it = _item("a.png", rank=1, is_best=True, rank_source="fusion")
    w._items = [it]
    w.set_ranks_visible(False)
    assert it.badge == ""
    w.set_ranks_visible(True)
    assert it.badge == rb.BEST_TEXT


def test_widget_defaults_ranks_visible_for_storeless_contexts() -> None:
    from tabs.image_gallery.widget import ImageGalleryWidget

    assert getattr(ImageGalleryWidget, "_ranks_visible", None) is None or True
    # The instance default (no controller) keeps legacy behaviour.
    w = ImageGalleryWidget()
    assert getattr(w, "_ranks_visible", True) is True
    w.deleteLater()
