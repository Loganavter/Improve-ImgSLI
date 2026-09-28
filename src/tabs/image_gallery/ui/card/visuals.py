"""Visual helpers — rejected/badge, selection, fixed size (painter pipeline only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QGraphicsOpacityEffect, QSizePolicy

from PySide6.QtGui import QColor

from sli_ui_toolkit.managers import scaled_px


def _token_qcolor(token: str, fallback_hex: str) -> QColor:
    """Resolve theme token via sanctioned wrapper, fallback hex."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    return QColor(fallback_hex)


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor:
    """Resolve theme token via wrapper, fallback rgba."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    return QColor(*fallback_rgba)


def _card_border_color() -> QColor:
    """Default card edge: ``gallery.card.border`` → ``button.dialog.default.border``.

    Frozen seam: tokens only via ``try_resolve_theme_color``. Rule A: fallback
    keyed on ``is_dark()`` (light default) — ``#e2e4e8`` light / white@0.12
    dark (mockup 1px card edges, v2/v3/v4-light). The rejected/danger paths
    are untouched — only default borders route here.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for _tok in ("gallery.card.border", "button.dialog.default.border"):
            try:
                c = try_resolve_theme_color(mgr, _tok)
            except Exception:
                c = None
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
        try:
            _dark = bool(mgr.is_dark())
        except Exception:
            _dark = False
    except Exception:
        _dark = False
    if _dark:
        return QColor(255, 255, 255, 30)
    return QColor("#e2e4e8")


if TYPE_CHECKING:
    from sli_ui_toolkit.widgets import Button
    from tabs.image_gallery.models import GalleryItem


def apply_fixed_gallery_card_size(
    card: Button,
    width: int = 250,
    height: int = 170,
) -> None:
    """Pin card to fixed size 250×170 per real_design.md:2.3 (no underscale)."""
    # real_design.md demands 250px; scaled_px may underscale on small UiScale, clamp to at least spec
    w = scaled_px(width)
    h = scaled_px(height)
    # Never shrink below spec (145px bug)
    w = max(w, width)
    h = max(h, height)
    card.setFixedSize(w, h)
    card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def _apply_rejected_visuals(card: Button, item: GalleryItem) -> None:
    """Rejected = opacity 0.38 + strike-through (no toolkit badge).

    No mode switch on the corner: the only rejected signals are the dim +
    strike-through (card actions live in the right-click context menu). The toolkit ``setBadge``
    pill is never used here (it painted an almost-glyphless red oval).
    """

    try:
        rejected = bool(getattr(item, "rejected", False))
    except Exception:
        rejected = False
    try:
        is_best = bool(getattr(item, "is_best", False))
    except Exception:
        is_best = False

    # Badge priority: #N rank pills only. The leader-star and tie-break
    # pills were dropped by design verdict (#N stays): tie-pending items fall
    # through to the rank path (#N if ranked, else no badge), and the
    # leader (is_best / rank 1) shows its #N. Rejected sets no toolkit
    # badge (no corner mode switch); dim + strike-through carry the
    # rejected signal.
    try:
        if rejected:
            try:
                card.setBadge(None)
            except Exception:
                pass
            try:
                card.setBorderColor(_token_rgba_qcolor("button.dialog.default.border", (255, 255, 255, 30)))
            except Exception:
                pass
            try:
                card._gallery_badge = None  # type: ignore[attr-defined]
            except Exception:
                pass
        else:
            # Left top per spec — overlay for ranked cards, clear toolkit right badge.
            # No accent outline: the frame stays the default card border.
            cr = getattr(item, "crown_rank", None)
            rank_val = cr if cr is not None else getattr(item, "rank", None)
            if rank_val is None and is_best:
                # Leader without an explicit rank still shows #1.
                rank_val = 1
            if rank_val is not None:
                try:
                    badge_text = f"#{int(rank_val)}"
                except Exception:
                    badge_text = str(rank_val)
                try:
                    card.setBadge(None)
                except Exception:
                    pass
                try:
                    card._gallery_badge = badge_text  # type: ignore[attr-defined]
                    rank_bg = _token_qcolor("button.toggle.background.checked", "#555555")
                    # Rank pill text is always black (both themes).
                    card._gallery_badge_style = (True, rank_bg, rank_bg, QColor("#000000"))  # type: ignore[attr-defined]
                    card.setBorderColor(_card_border_color())
                except Exception:
                    pass
            else:
                try:
                    card.setBadge(None)
                except Exception:
                    pass
                try:
                    card._gallery_badge = None  # type: ignore[attr-defined]
                    card.setBorderColor(_card_border_color())
                except Exception:
                    pass
    except Exception:
        pass

    # Strike-through via Button style API (painter pipeline) — no QSS.
    try:
        if hasattr(card, "set_show_strike_through"):
            card.set_show_strike_through(bool(rejected))
    except Exception:
        pass

    # Rejected must remain clickable: dim is painter-level (overlay wash
    # in painters._gallery_rejected_dim) + strike-through. No
    # QGraphicsOpacityEffect here on purpose: the effect dims the whole
    # subtree INCLUDING the hover capsule (child of the card), washing it
    # out to near-invisible on rejected cards. The wash dims only the
    # card's own paint; children stay crisp.
    # Ensure enabled (A2 spec: убрать setEnabled(False)).
    try:
        card.setEnabled(True)
    except Exception:
        pass

    # Drop any legacy opacity effect (e.g. from pool-recycled cards that
    # were dimmed before the painter wash replaced the effect).
    try:
        current_effect = card.graphicsEffect()
        if isinstance(current_effect, QGraphicsOpacityEffect):
            card.setGraphicsEffect(None)
    except Exception:
        pass


# Backwards-compat aliases for grid_view and selection overlay.

def gallery_selection_accent(theme_manager=None):  # type: ignore[no-untyped-def]
    try:
        from ui.widgets.shelf.selection import selection_accent_color

        return selection_accent_color(theme_manager)
    except Exception:
        # S2-12: accent via theme token chain, theme-aware fallback for offscreen tests.
        from tabs.image_gallery.ui.card.dots import _accent_color

        return _accent_color()


def apply_gallery_selection(card: Button, selected: bool, accent=None) -> None:  # type: ignore[no-untyped-def]
    try:
        from ui.widgets.shelf.selection import apply_card_selected

        if accent is None:
            accent = gallery_selection_accent()
        apply_card_selected(card, bool(selected), accent=accent)
    except Exception:
        # Fallback: toggle a simple override bg when selected.
        try:
            if selected:
                if accent is None:
                    accent = gallery_selection_accent()
                card.set_override_bg_color(accent)
            else:
                card.set_override_bg_color(None)
        except Exception:
            pass
