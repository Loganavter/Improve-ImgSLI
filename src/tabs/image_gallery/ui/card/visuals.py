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
    """Rejected = opacity 0.38 + strike-through + ✕ badge (setBadge).

    Stage 3 extension: ``AI tie-break…`` pending badge takes precedence
    over normal rank badges — shown on both top-2 candidates until resolved,
    degraded silent-but-visible (cleared) if VLM unresolved.

    Opacity 0.38 is imitated via ``setEnabled(False)`` (disabled dim) plus
    ``set_show_strike_through`` and ``ButtonRow(strikethrough=True)`` — the
    latter is marked in ``_text_rows``. Badge: ``★ BEST`` accent pill or
    ``#N`` gray via ``Button.setBadge``/``setBadgeStyle``. Crown ``★ BEST``
    uses badge as well — rejected takes precedence, tie-break pending takes
    even higher precedence (unless rejected).
    """
    from PySide6.QtGui import QColor as _QColor

    # Lazy imports to avoid cycles at module import.
    from tabs.image_gallery.ui.card.dots import (
        _accent_color,
        _error_line_color,
        _token_color,
    )

    # Local theme helpers already defined at module level (_token_qcolor etc.)
    # but keep _QColor alias for accent lighter derivation.

    try:
        rejected = bool(getattr(item, "rejected", False))
    except Exception:
        rejected = False
    try:
        is_best = bool(getattr(item, "is_best", False))
    except Exception:
        is_best = False
    try:
        tie_pending = bool(getattr(item, "vlm_tie_pending", False))
    except Exception:
        tie_pending = False

    # Badge priority: rejected (right top red) > AI tie-break (right) > BEST/#N (left per real_design.md:2.5)
    try:
        if rejected:
            card.setBadge("✕")
            try:
                _danger = _error_line_color()
                card.setBadgeStyle(
                    filled=True,
                    background_color=_danger,
                    border_color=_danger,
                    text_color=_token_qcolor("button.primary.text", "#ffffff"),
                )
                card.setBorderColor(_token_rgba_qcolor("button.dialog.default.border", (255, 255, 255, 30)))
            except Exception:
                pass
            try:
                card._gallery_badge = None  # type: ignore[attr-defined]
            except Exception:
                pass
        elif tie_pending:
            # S2 mockup: AI tie-break is an in-thumbnail pill (left overlay,
            # like ★ BEST) — not a top-right toolkit badge.
            try:
                card.setBadge(None)
            except Exception:
                pass
            try:
                _accent = _accent_color()
                _accent_text = _QColor(_accent)
                try:
                    _accent_text = _accent_text.lighter(150)
                except Exception:
                    pass
                card._gallery_badge = "AI tie-break…"  # type: ignore[attr-defined]
                card._gallery_badge_style = (False, None, _accent, _accent_text)  # type: ignore[attr-defined]
                card.setBorderColor(_token_rgba_qcolor("button.dialog.default.border", (255, 255, 255, 30)))
            except Exception:
                pass
        elif is_best or (not rejected and not tie_pending and getattr(item, "rank", None) == 1) or (not rejected and not tie_pending and getattr(item, "crown_rank", None) == 1):
            # Left top per spec — overlay for leader (is_best or rank 1), clear toolkit right badge + accent border 2px
            try:
                card.setBadge(None)
            except Exception:
                pass
            try:
                card._gallery_badge = "★ BEST"  # type: ignore[attr-defined]
                card._gallery_badge_style = (True, _accent_color(), _accent_color(), _token_qcolor("button.primary.text", "#ffffff"))  # type: ignore[attr-defined]
                # Accent border 2px for BEST
                try:
                    card.setBorderColor(_accent_color())
                    card.setProperty("borderWidth", 2)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            cr = getattr(item, "crown_rank", None)
            rank_val = cr if cr is not None else getattr(item, "rank", None)
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
                    card._gallery_badge_style = (True, rank_bg, rank_bg, _token_qcolor("gallery.stats.text", "#dfdfdf"))  # type: ignore[attr-defined]
                    card.setBorderColor(_token_rgba_qcolor("button.dialog.default.border", (255, 255, 255, 30)))
                except Exception:
                    pass
            else:
                try:
                    card.setBadge(None)
                except Exception:
                    pass
                try:
                    card._gallery_badge = None  # type: ignore[attr-defined]
                    card.setBorderColor(_token_rgba_qcolor("button.dialog.default.border", (255, 255, 255, 30)))
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

    # Rejected must remain clickable: only QGraphicsOpacityEffect 0.38 + strike.
    # Ensure enabled (A2 spec: убрать setEnabled(False)).
    try:
        card.setEnabled(True)
    except Exception:
        pass

    # Keep QGraphicsOpacityEffect as additional dim for fidelity (0.38) via ThemeManager tokens (no manual palette).
    try:
        current_effect = card.graphicsEffect()
        if rejected:
            if not isinstance(current_effect, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(card)
                eff.setOpacity(0.38)
                card.setGraphicsEffect(eff)
            else:
                current_effect.setOpacity(0.38)
        else:
            if isinstance(current_effect, QGraphicsOpacityEffect):
                # Remove effect to restore full opacity.
                card.setGraphicsEffect(None)
        # If rejected, disabled + effect together give 0.38 look; effect alone
        # also works when disabled is not enough. Keep both for robustness.
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
