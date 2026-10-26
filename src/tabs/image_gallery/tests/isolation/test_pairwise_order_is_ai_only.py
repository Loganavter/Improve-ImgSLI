"""INVARIANT: a pairwise (VLM A/B) order lands ONLY in the AI domain.

Owner decision (2026-10-26): the VLM pairwise refinement moved to the AI
domain. The pass's gate is not the only protection — the landing is
asynchronous (the worker reports after the toolbar may already have left
``ai``), so the ONE rank primitive refuses an explicit ``pairwise_order``
unless the live judgment domain is ``ai``.

Falsification story (red without the guard at the top of
``GalleryController._apply_fusion_ranks``): the same call under ``algorithms``
forwards ``b > a`` into ``rank_fusion.rank_series`` and swaps the measured
fusion ranks — a model verdict overwriting the Algorithms order. The AI half
below is the non-vacuity control: the identical call there DOES flip the ranks,
so the Algorithms assertion is not passing because the order was inert.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, Series


class _Widget:
    """Bare widget surface the rank primitive touches."""

    def refresh_card(self, _item) -> None:
        pass

    def refresh_cards(self, _items) -> None:
        pass

    def set_ranks_visible(self, _flag) -> None:
        pass

    def set_rank_provenance(self, _src, **_kwargs) -> None:
        pass


def _owner(domain: str):
    """A controller double whose REAL rank primitive is the subject."""
    ctl = GalleryController.__new__(GalleryController)
    a, b = _items()
    series = Series(id="series_1", members=[a, b])
    ctl.state = SimpleNamespace(
        items=[a, b],
        series=[series],
        mode="camera",
        algorithms_profile=None,
        ai_profile=None,
    )
    ctl.widget = _Widget()
    ctl._folder_gen = 0
    ctl._metrics_settled_gen = 0
    ctl._judgment_domain = domain
    ctl._domain_epoch = 1
    return ctl, series, a, b


def _items() -> tuple[GalleryItem, GalleryItem]:
    """``a`` leads on the measured axis, so the fusion order is ``a > b``."""
    a = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    a.metrics.update({"sharpness": 204.0})
    b = GalleryItem(path=Path("/gallery/b.png"), mtime_ns=1)
    b.metrics.update({"sharpness": 200.0})
    return a, b


def _pairwise_b_first(b: GalleryItem, a: GalleryItem) -> tuple[str, str]:
    return (str(b.path), str(a.path))


def test_a_pairwise_order_is_refused_under_algorithms() -> None:
    owner, series, a, b = _owner("algorithms")
    GalleryController._apply_fusion_ranks(owner, owner.state.series)
    assert (a.rank, b.rank) == (1, 2), "fixture sanity: fusion leads with a.png"

    GalleryController._apply_fusion_ranks(
        owner, owner.state.series, pairwise_order=_pairwise_b_first(b, a)
    )

    assert (a.rank, b.rank) == (1, 2), (
        "a pairwise (model) order was applied under Algorithms: "
        f"a={a.rank} b={b.rank}"
    )
    assert (a.rank_source, b.rank_source) == ("fusion", "fusion")


def test_the_same_order_lands_in_the_ai_domain() -> None:
    """Non-vacuity: in the domain that owns it, the order really is applied."""
    owner, series, a, b = _owner("ai")
    GalleryController._apply_fusion_ranks(owner, owner.state.series)
    assert (a.rank, b.rank) == (1, 2)

    GalleryController._apply_fusion_ranks(
        owner, owner.state.series, pairwise_order=_pairwise_b_first(b, a)
    )

    assert (b.rank, a.rank) == (1, 2), (
        "the AI domain must still land its pairwise order: "
        f"a={a.rank} b={b.rank}"
    )
