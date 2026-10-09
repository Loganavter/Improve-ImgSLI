"""Single source of truth for the gallery rank badge.

Every gallery surface that shows a rank badge — the grid cards
(``ui/card/visuals.py``), the quick-look series strip
(``ui/quick_look/strip.py``) and the list rows (``ui/list/regions.py``) —
derives its label from the *same* ``GalleryItem`` fields and the *same*
priority rule. Before this module each surface re-implemented the rule and
kept it in sync by comment, so they drifted (a leader showed ``#N`` on a
card but a star in the list; only the strip knew ``SOURCE``/``…``). They now
call :func:`resolve_rank_badge` and read the fields they need; presentation
(paint vs pill vs inline text) stays per-surface.

Pure data, no Qt (safe off the GUI thread and in headless tests).

Fields (``GalleryItem``, populated by triage):
``crown_rank`` (crown verdict) wins over ``rank``; ``is_best`` is the leader
flag; ``rejected`` marks a rejected item.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Badge kinds.
KIND_RANK = "rank"
KIND_SOURCE = "source"
KIND_NONE = "none"


@dataclass(frozen=True)
class RankBadge:
    """Resolved rank badge for one item.

    ``text`` is the primary label (``"#N"`` / ``"SOURCE"`` / ``""``).
    ``kind`` names the branch (``rank``/``source``/``none``).
    ``rank`` is the resolved number (``crown_rank ?? rank``, or ``1`` for a
    leader when ``leader_as_rank``); ``None`` when there is none.
    ``is_best`` / ``rejected`` are surfaced so each surface can add its own
    affordance (list ``★``/``✕``, card/strip suppression) without
    re-deriving them.
    """

    text: str
    kind: str
    rank: int | None
    is_best: bool
    rejected: bool


def resolve_rank_badge(
    item,
    *,
    is_source: bool = False,
    leader_as_rank: bool = True,
) -> RankBadge:
    """Resolve the rank badge for *item* (never raises).

    Priority: ``is_source`` ("SOURCE") > rank (``"#N"``) > none.
    ``crown_rank`` wins over ``rank``; a leader (``is_best``) with no
    explicit rank resolves to ``#1`` when ``leader_as_rank`` is true
    (cards/strip) and to no number when false (list, which shows its own
    ``★``).

    ``rejected`` is *reported*, never folded into ``text`` — cards/strip
    suppress the badge on it, the list keeps the rank and appends ``✕``.
    """
    is_best = False
    rejected = False
    try:
        is_best = bool(getattr(item, "is_best", False))
        rejected = bool(getattr(item, "rejected", False))
    except Exception:
        pass

    if is_source:
        return RankBadge("SOURCE", KIND_SOURCE, None, is_best, rejected)

    rank_val = None
    try:
        rank_val = getattr(item, "crown_rank", None)
        if rank_val is None:
            rank_val = getattr(item, "rank", None)
    except Exception:
        rank_val = None
    try:
        rank_i = int(rank_val) if rank_val is not None else None
    except Exception:
        rank_i = None
    if rank_i is None and is_best and leader_as_rank:
        rank_i = 1
    if rank_i is not None:
        return RankBadge(f"#{rank_i}", KIND_RANK, rank_i, is_best, rejected)
    return RankBadge("", KIND_NONE, None, is_best, rejected)


__all__ = ["RankBadge", "resolve_rank_badge", "KIND_RANK", "KIND_SOURCE", "KIND_NONE"]
