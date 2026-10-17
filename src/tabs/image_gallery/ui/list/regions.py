"""List-row region builders — thumb + title + meta (no grid imports)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from sli_ui_toolkit.widgets import ButtonRegion, ButtonRow

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem


def item_unreadable(item: GalleryItem) -> bool:
    """Unreadable/corrupt item: thumbnail decode failed or an unreadable error.

    Item-level predicate owned here (models on this tree does not provide
    it yet; logic mirrors grid ``ui/card/regions._item_unreadable`` by
    value, never by import — list rows must not import ``ui/card/*``).
    Both grid covers and list thumbs show the ``!`` plate for it.
    """
    try:
        ts = getattr(item, "thumbnail_status", None)
        if ts is not None and str(getattr(ts, "value", ts)).lower() == "error":
            return True
    except Exception:
        pass
    try:
        err = getattr(item, "analysis_error", None)
        if err:
            low = str(err).lower()
            if any(word in low for word in ("unreadable", "corrupt", "поврежд")):
                return True
    except Exception:
        pass
    return False


def _badges_text(item: GalleryItem, translate=None) -> str:
    """Inline badges: the precomputed ``item.badge`` + ★ (leader) + ✕ (rejected).

    The badge string is computed once by ``services.rank_badge.stamp_badges``;
    the list only adds its own ★/✕ affordances and never re-derives it. The
    SOURCE badge is stamped English once, so it is localized at render via the
    injected list translator (same key as the card/strip badge).
    """
    parts: list[str] = []
    text = str(getattr(item, "badge", "") or "")
    _kind = str(getattr(item, "badge_kind", "none") or "none")
    if text:
        from tabs.image_gallery.services.rank_badge import KIND_BEST, KIND_SOURCE

        if _kind == KIND_SOURCE:
            text = _tr(translate, "image_gallery.badge.source", text)
        elif _kind == KIND_BEST:
            text = _tr(translate, "image_gallery.badge.best", text)
        parts.append(text)
    # The leader's ★ is redundant when the shared badge already says ★ BEST.
    if bool(getattr(item, "is_best", False)) and _kind != "best":
        parts.append("★")
    if bool(getattr(item, "rejected", False)):
        parts.append("✕")
    return " ".join(parts)


def _tr(translate, key: str, default: str) -> str:
    """List-meta i18n lookup (fail-open to the EN default)."""
    if callable(translate):
        try:
            return str(translate(key, default))
        except Exception:
            pass
    return default


def _list_text_rows(item: GalleryItem, translate=None) -> list[ButtonRow]:
    """ONE title row: name + badges inline, full-height centered (compact)."""
    text = item.name
    badges = _badges_text(item, translate)
    if badges:
        text = f"{text} {badges}"
    # Static truncated text (same reason as grid cards: the 60fps
    # marquee storm never paid off — task-marquee-mass-opt-research).
    return [ButtonRow(text=text, size=16, weight="normal", h_align=Qt.AlignmentFlag.AlignLeft, marquee=False, elide=True)]


def _list_meta_rows(item: GalleryItem, translate=None) -> list[ButtonRow]:
    """No text meta rows: the meta region hosts the metric-axis dots.

    The old artifact/VLM status text (Artifacts / Minor / tie…) is gone by
    product decision; the dots are painted by the row overlay painter and the
    region remains as the right-side layout slot.
    """
    return []


def _thumb_region(item: GalleryItem) -> ButtonRegion:
    """Fixed-width cover thumb, full height (unreadable → '!')."""
    thumb = getattr(item, "thumbnail", None)
    if thumb is not None and not thumb.isNull():
        return ButtonRegion(id="thumb", pixmap=thumb, image_fill="cover", weight=0.0,
                            group="card", corner_radii=(8, 0, 0, 8))
    try:
        unreadable = bool(item_unreadable(item))
    except Exception:
        unreadable = False
    return ButtonRegion(id="thumb", text="!" if unreadable else "", weight=0.0,
                        group="card", corner_radii=(8, 0, 0, 8))
