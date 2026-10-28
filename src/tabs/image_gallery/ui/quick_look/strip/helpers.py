"""Quick Look series-strip helpers — geometry, ranking, family, fingerprint.

Split out of the former ``ui/quick_look/strip.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged.
"""

from __future__ import annotations

from pathlib import Path

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonFamily


def _strip_thumb_pitch(overlay) -> int:
    """One-thumb scroll pitch in px (live geometry, no size assumptions).

    Container width + layout spacing; falls back to the W6 66+10 budget
    when nothing is built yet. Never raises.
    """
    try:
        buttons = list(getattr(overlay, "_strip_buttons", None) or [])
        if buttons:
            try:
                w = int(buttons[0].width())
            except Exception:
                w = 0
            try:
                s = int(overlay._strip_layout.spacing())
            except Exception:
                s = 0
            if w > 0:
                return max(1, w + max(0, s))
    except Exception:
        pass
    try:
        return max(1, int(scaled_px(66)) + int(scaled_px(10)))
    except Exception:
        return 76
def _strip_wheel_step(event, pitch: int = 76) -> int | None:
    """Horizontal scroll px from a wheel event over the strip (pure).

    Prefers angleDelta.x; falls back to angleDelta.y (a plain vertical
    wheel over a horizontal filmstrip scrolls it — filmstrip convention);
    high-resolution pixel deltas map 1:1. One 120-unit notch moves exactly
    one thumb pitch (deliberately NOT lines*singleStep, which jumps three
    thumbs per notch). Sign follows Qt convention (positive delta scrolls
    toward the start). None when the event carries no scrollable delta.
    Never raises.
    """
    try:
        step = max(1, int(pitch))
    except Exception:
        step = 76
    try:
        try:
            pd = event.pixelDelta()
            if pd is not None and (int(pd.x()) or int(pd.y())):
                dx = int(pd.x())
                return -dx if dx else -int(pd.y())
        except Exception:
            pass
        try:
            ad = event.angleDelta()
            if ad is None:
                return None
            raw = int(ad.x()) or int(ad.y())
        except Exception:
            return None
        if not raw:
            return None
        return -int(round(raw / 120.0 * step))
    except Exception:
        return None
def open_strip_thumb_menu(overlay, widget, path=None) -> bool:
    """Open the shared grid card menu for a strip thumb/pill (grid parity).

    Wired to each thumb's ``rightClicked`` — the exact signal the grid cards
    use (see ``ui/card/factory.py`` ``_bind_gallery_card``) — so the strip menu is
    produced by the same proven signal path instead of a release-time filter
    branch. Resolves the item path from the widget's ``gallery_path``
    property, else from the ``quicklook_strip_<idx>`` / ``quicklook_rank_<idx>``
    object-name index. True when a menu was opened. Never raises.
    """
    try:
        if path is None:
            try:
                path = str(widget.property("gallery_path") or "")
            except Exception:
                path = ""
        if not path:
            try:
                idx = int(str(widget.objectName() or "").rsplit("_", 1)[-1])
                items = list(getattr(overlay, "_series_items", None) or [])
                if 0 <= idx < len(items):
                    path = str(getattr(items[idx], "path", "") or "")
            except Exception:
                path = ""
        if not path:
            return False
        try:
            from PySide6.QtGui import QCursor

            gp = QCursor.pos()
        except Exception:
            gp = None
        try:
            from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

            owner = getattr(overlay, "_owner", None)
            popup_gallery_card_context_menu(widget, owner, Path(path), global_pos=gp)
            return True
        except Exception:
            return False
    except Exception:
        return False
def _strip_rank_text_and_style(m, overlay=None):
    """Rank pill content for one series member (badge-button input).

    Renders ``item.badge`` / ``item.badge_kind`` — computed ONCE by
    ``services.rank_badge.stamp_badges`` and read verbatim here (the strip
    never re-derives the badge from flags). Priority: no badge on rejected.
    The SOURCE string is stamped English once upstream, so it is localized at
    render through the overlay translator (same key as the card badge,
    ``image_gallery.badge.source``); ``#N`` needs no translation. Returns
    ``(text, outline, text_color)`` — the pill fills white with ``outline``
    as its 1px border — or None when no pill is shown. Never raises.
    """
    try:
        from PySide6.QtGui import QColor as _QC

        from tabs.image_gallery.services.rank_badge import KIND_BEST, KIND_SOURCE
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _strip_dark
        from tabs.image_gallery.ui.quick_look.helpers import _token_color as _strip_token

        text = str(getattr(m, "badge", "") or "")
        kind = str(getattr(m, "badge_kind", "none") or "none")
        if not text or bool(getattr(m, "rejected", False)):
            return None  # no pill — dim effect carries the rejected signal
        _strip_is_dark = _strip_dark()
        _ink = _QC("#000000")
        # Every translated kind renders through the SAME key the card badge
        # uses (``ui/card/visuals.py``) — the stamped text is English by design
        # (``services/rank_badge.stamp_badges``) and is localized here only.
        _kind_key = {
            KIND_SOURCE: "image_gallery.badge.source",
            KIND_BEST: "image_gallery.badge.best",
        }.get(kind)
        if _kind_key is not None:
            _tr = getattr(overlay, "_tr", None)
            if callable(_tr):
                try:
                    text = str(_tr(_kind_key, text))
                except Exception:
                    pass
        if kind == KIND_SOURCE:
            _gold = _strip_token("gallery.status.warn", "#b77900" if not _strip_is_dark else "#d9a441")
            return (text, _gold, _ink)
        _rank_bg = _strip_token("button.toggle.background.checked", "#555555")
        return (text, _rank_bg, _ink)
    except Exception:
        return None


def _strip_badge_fit(text: str, *, scaled=None, px=None):
    """Fit one rank-pill label inside its 66px thumb container.

    Returns ``(font_px, width_scaled, elide)``.

    The container is the clip rect: a child wider than it is cut off (and the
    old pin clamped a too-wide pill to the LEFT edge, so a long localized
    label was both clipped and visibly off-centre — live report 2026-10-22,
    ru ``ИСТОЧНИК``). Try the design font ladder (``BADGE_FONT_SIZES``) and
    take the first face whose ``advance + BADGE_H_PAD`` fits
    ``thumb - 2px``; if even the smallest does not, cap at the container and
    let the toolkit elide (``ButtonRow(elide=True)``) — never a silent cut.

    Design px in, scaled px out (the same contract as the pill's
    ``_design_fixed_size``), so a UiScale change re-derives the same fit.
    """
    try:
        from PySide6.QtGui import QFontMetrics

        from sli_ui_toolkit.managers import scaled_px, ui_font

        from tabs.image_gallery.services.rank_badge import (
            BADGE_FONT_SIZES,
            BADGE_H_PAD,
            BADGE_MIN_WIDTH,
        )

        text = str(text or "")
        #: Strip thumb is a 66px design square (W6 svg pitch 76 = 66 + 10 gap);
        #: one design px of breathing room each side keeps the pill inside the
        #: container that clips it.
        thumb_room = scaled_px(64)
        pad = scaled_px(BADGE_H_PAD)
        min_w = scaled_px(BADGE_MIN_WIDTH)
        for size in BADGE_FONT_SIZES:
            try:
                adv = int(QFontMetrics(ui_font(pixel_size=int(size))).horizontalAdvance(text))
            except Exception:
                continue
            want = max(min_w, adv + pad)
            if want <= thumb_room:
                return int(size), want, False
        return int(BADGE_FONT_SIZES[-1]), max(min_w, thumb_room), True
    except Exception:
        return 11, 0, False
def _strip_family(overlay):
    """Shared-hover family for strip thumbs + rank pills (created once).

    One family for both: hovering a thumb lights its pill (and siblings),
    hovering a pill lights the thumbs — the strip reads as one control.
    """
    try:
        fam = getattr(overlay, "_strip_family", None)
        if fam is None:
            fam = ButtonFamily(overlay)
            try:
                fam.setSharedHover(True)
            except Exception:
                pass
            overlay._strip_family = fam
        return fam
    except Exception:
        return None
def _strip_family_add(overlay, button) -> None:
    """Link a strip button into the shared-hover family. Never raises."""
    try:
        fam = _strip_family(overlay)
        if fam is not None and button is not None:
            fam.addButton(button)
    except Exception:
        pass
def _repin_strip_rank_buttons(overlay) -> None:
    """Pin each rank pill centered on its thumb's bottom edge (half out).

    Rank buttons are layout-external children of the thumb container — the
    container reserves the overhang below the thumb — so container resizes
    never move them: re-pin after rebuilds and host resizes. Never raises.
    """
    try:
        containers = list(getattr(overlay, "_strip_buttons", None) or [])
    except Exception:
        return
    for idx, container in enumerate(containers):
        try:
            thumb = container.findChild(Button, f"quicklook_strip_{idx}")
            pill = container.findChild(Button, f"quicklook_rank_{idx}")
            if thumb is None or pill is None:
                continue
            tg = thumb.geometry()
            # Fresh pills report 0 live width until shown — but the pill
            # size is fixed at build, so pin from the minimum (valid
            # immediately), hint as the last resort.
            try:
                pw = int(pill.minimumWidth()) or int(pill.sizeHint().width())
            except Exception:
                pw = 0
            try:
                ph = int(pill.minimumHeight()) or int(pill.sizeHint().height())
            except Exception:
                ph = 0
            if pw <= 0 or ph <= 0:
                continue
            # Center on the thumb's centre line. The old form clamped the
            # left edge at 0, so a pill wider than its thumb (a long localized
            # label) sat flush left and read as off-centre; the fit helper now
            # keeps the pill inside the thumb, and this arithmetic makes an
            # odd width land on the same centre (QRect.center uses (w-1)//2).
            pill.move(
                tg.center().x() - (pw - 1) // 2,
                tg.y() + max(0, tg.height() - ph // 2),
            )
        except Exception:
            continue
def _strip_rank_key(m) -> tuple:
    """Badge identity for one series member (rank-pill input).

    Reads the precomputed ``item.badge`` — the strip fingerprint tracks the
    exact string the pill renders (no per-surface re-derivation).
    """
    return (
        str(getattr(m, "badge", "") or ""),
        str(getattr(m, "badge_kind", "none") or "none"),
        bool(getattr(m, "rejected", False)),
    )
def _strip_fingerprint(overlay) -> tuple:
    """Structural identity of the strip (everything a FULL rebuild consumes).

    Per-walk dynamic state (checked + border on old/new idx) is deliberately
    EXCLUDED — a walk changes only that, which the in-place refresh covers.
    Anything else (triage flags, ranks, theme, scale, series/source change)
    mismatches and falls back to today's full rebuild.
    """
    try:
        items = list(getattr(overlay, "_series_items", None) or [])
    except Exception:
        return ()
    try:
        paths = tuple(str(getattr(m, "path", "") or "") for m in items)
        rejected = tuple(bool(getattr(m, "rejected", False)) for m in items)
        ranks = tuple(_strip_rank_key(m) for m in items)
        source = str(getattr(overlay, "_source_path", None) or "")
        try:
            from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _fp_is_dark

            dark = bool(_fp_is_dark())
        except Exception:
            dark = True
        try:
            sp = int(scaled_px(66))
        except Exception:
            sp = 66
        return (paths, rejected, ranks, source, dark, sp)
    except Exception:
        return ()
