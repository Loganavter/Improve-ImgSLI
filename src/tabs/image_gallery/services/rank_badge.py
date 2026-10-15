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
flag; ``rejected`` (or ``triage_rejected`` — see ``triage.is_rejected``)
marks a rejected item.

The badge also carries *provenance*: which ranker produced the number
(``item.rank_source`` — ``fusion``/``jev``/``manual``), so a surface can say
**Algorithms** vs **AI (Jev)** vs **Manual**. An item with no measured rank
renders no number (never ``#0``); see
``plan-gallery-rank-backends-2026-10-15``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Badge kinds.
KIND_RANK = "rank"
KIND_SOURCE = "source"
KIND_NONE = "none"

#: Ranker provenance tokens stored on ``GalleryItem.rank_source`` — the ranker
#: that produced the number. ``fusion`` = the deterministic Algorithms floor
#: (metric fusion), ``jev`` = the opt-in, non-deterministic AI ranking,
#: ``manual`` = the user picked the winner (Keep/Make best).
#: See ``plan-gallery-rank-backends-2026-10-15``.
RANK_SOURCE_FUSION = "fusion"
RANK_SOURCE_JEV = "jev"
RANK_SOURCE_MANUAL = "manual"
RANK_SOURCES: tuple[str, ...] = (
    RANK_SOURCE_FUSION,
    RANK_SOURCE_JEV,
    RANK_SOURCE_MANUAL,
)

#: ``rank_source`` → (i18n key, English default). Surfaces translate with the
#: key; pure-data callers fall back to the default. Keys live in the tab
#: catalogue under ``image_gallery.rank``.
RANK_SOURCE_LABEL: dict[str, tuple[str, str]] = {
    RANK_SOURCE_FUSION: ("image_gallery.rank.source.algorithms", "Algorithms"),
    RANK_SOURCE_JEV: ("image_gallery.rank.source.ai", "AI (Jev)"),
    RANK_SOURCE_MANUAL: ("image_gallery.rank.source.manual", "Manual"),
}

#: Badge geometry (design px) — shared by the grid-card painter
#: (``ui/card/painters.py``) and the quick-look strip pill
#: (``ui/quick_look/strip.py``) so the two cannot drift in size: a compact
#: pill = text + ``BADGE_H_PAD`` horizontal breathing room, at least
#: ``BADGE_MIN_WIDTH`` wide, ``BADGE_HEIGHT`` tall, ``BADGE_RADIUS`` corners.
BADGE_MIN_WIDTH = 28
BADGE_H_PAD = 12
BADGE_HEIGHT = 18
BADGE_RADIUS = 9


@dataclass(frozen=True)
class RankBadge:
    """Resolved rank badge for one item.

    ``text`` is the primary label (``"#N"`` / ``"SOURCE"`` / ``""``).
    ``kind`` names the branch (``rank``/``source``/``none``).
    ``rank`` is the resolved number (``crown_rank ?? rank``, or ``1`` for a
    leader when ``leader_as_rank``); ``None`` when there is none.
    ``is_best`` / ``rejected`` are surfaced so each surface can add its own
    affordance (list ``★``/``✕``, card/strip suppression) without
    re-deriving them. ``source`` / ``provenance`` name the ranker
    (``Algorithms`` | ``AI (Jev)`` | ``Manual``; see :func:`rank_provenance`).
    """

    text: str
    kind: str
    rank: int | None
    is_best: bool
    rejected: bool
    #: The ranker behind ``rank`` (``rank_source``): "fusion" | "jev" |
    #: "manual", or ``None`` when the item carries no rank. Surfaces that show
    #: provenance read this (and translate via :func:`rank_provenance`).
    source: str | None = None
    #: English default provenance label for ``source`` ("" when unranked/unknown)
    #: — the translator-less seam; translated text comes from
    #: :func:`rank_provenance`.
    provenance: str = ""


def _int_rank(value) -> int | None:
    """Coerce *value* to a rank ≥ 1, else ``None`` (never fabricates ``#0``)."""
    try:
        i = int(value)
    except Exception:
        return None
    return i if i >= 1 else None


def _has_rank(item) -> bool:
    """True when *item* carries any rank signal (number or leader flag)."""
    try:
        if _int_rank(getattr(item, "crown_rank", None)) is not None:
            return True
        if _int_rank(getattr(item, "rank", None)) is not None:
            return True
        return bool(getattr(item, "is_best", False))
    except Exception:
        return False


def rank_source_of(item, *, domain: str | None = None) -> str | None:
    """Which ranker produced *item*'s rank, or ``None`` when it has none.

    An explicit ``rank_source`` ("fusion"|"jev"|"manual") wins; otherwise a
    ranked item falls back to *domain* ("ai" → Jev, anything else → the
    Algorithms floor, which owns determinism per the plan).
    """
    src = ""
    try:
        src = str(getattr(item, "rank_source", "") or "").strip().lower()
    except Exception:
        src = ""
    if src in RANK_SOURCES:
        return src
    if not _has_rank(item):
        return None
    dom = str(domain or "").strip().lower()
    return RANK_SOURCE_JEV if dom == "ai" else RANK_SOURCE_FUSION


def rank_provenance(
    item,
    *,
    domain: str | None = None,
    translate=None,
) -> str:
    """Provenance label for *item* ("Algorithms"/"AI (Jev)"/"Manual").

    Translated through *translate* (a ``translate(key, default)`` callable) when
    given, else the English default. Returns "" when no ranker applies. Never
    raises.
    """
    src = rank_source_of(item, domain=domain)
    if src is None:
        return ""
    key, default = RANK_SOURCE_LABEL[src]
    if translate is not None:
        try:
            return str(translate(key, default))
        except Exception:
            return default
    return default


def resolve_rank_badge(
    item,
    *,
    is_source: bool = False,
    leader_as_rank: bool = True,
    domain: str | None = None,
) -> RankBadge:
    """Resolve the rank badge for *item* (never raises).

    Priority: ``is_source`` ("SOURCE") > rank (``"#N"``) > none.
    ``crown_rank`` wins over ``rank``; a leader (``is_best``) with no
    explicit rank resolves to ``#1`` when ``leader_as_rank`` is true
    (cards/strip) and to no number when false (list, which shows its own
    ``★``).

    ``rejected`` is *reported*, never folded into ``text`` — cards/strip
    suppress the badge on it, the list keeps the rank and appends ``✕``.

    ``domain`` ("algorithms"|"ai") is the fallback ranker when an item has a
    rank but no explicit ``rank_source``; the resolved ``source``/``provenance``
    let a surface state *which ranker* produced the number.
    """
    is_best = False
    rejected = False
    try:
        # Owner: triage.is_rejected (OR of both flags). Mirrored inline —
        # this module stays dependency-free (pure data, no triage import).
        is_best = bool(getattr(item, "is_best", False))
        rejected = bool(
            getattr(item, "rejected", False) or getattr(item, "triage_rejected", False)
        )
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
    rank_i = _int_rank(rank_val)
    if rank_i is None and is_best and leader_as_rank:
        rank_i = 1
    if rank_i is not None:
        source = rank_source_of(item, domain=domain)
        key, provenance = (
            RANK_SOURCE_LABEL[source] if source in RANK_SOURCE_LABEL else ("", "")
        )
        return RankBadge(
            f"#{rank_i}", KIND_RANK, rank_i, is_best, rejected, source, provenance
        )
    return RankBadge("", KIND_NONE, None, is_best, rejected)


def stamp_badges(items, source_path=None) -> None:
    """Compute and store the display badge on every item — ONE place.

    Every surface (grid card, quick-look strip, list row) renders
    ``item.badge`` / ``item.badge_kind`` verbatim; none re-derives the badge
    from flags, so adding a new badge kind (upscale/underscale/…) is a change
    in :func:`resolve_rank_badge` alone. Called from the single render path
    (``widget.set_triage``) with the current source, so a source/mode/rank
    change re-stamps. Never raises.
    """
    try:
        src = Path(str(source_path)) if source_path is not None else None
    except Exception:
        src = None
    for it in items or []:
        try:
            is_source = src is not None and Path(str(getattr(it, "path", ""))) == src
            badge = resolve_rank_badge(it, is_source=is_source)
            it.badge = badge.text
            it.badge_kind = badge.kind
            try:
                it.badge_source = badge.source
            except Exception:
                pass
        except Exception:
            try:
                it.badge = ""
                it.badge_kind = KIND_NONE
            except Exception:
                pass


__all__ = [
    "RankBadge",
    "resolve_rank_badge",
    "stamp_badges",
    "rank_source_of",
    "rank_provenance",
    "KIND_RANK",
    "KIND_SOURCE",
    "KIND_NONE",
    "RANK_SOURCE_FUSION",
    "RANK_SOURCE_JEV",
    "RANK_SOURCE_MANUAL",
    "RANK_SOURCES",
    "RANK_SOURCE_LABEL",
    "BADGE_MIN_WIDTH",
    "BADGE_H_PAD",
    "BADGE_HEIGHT",
    "BADGE_RADIUS",
]
