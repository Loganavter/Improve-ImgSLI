"""List-row visuals — theme tokens + rejected state (no grid imports).

Own token helpers (same chains as grid cards, copied, not imported) so a
grid-side token/policy change can never restyle list rows by accident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from sli_ui_toolkit.widgets import Button
    from tabs.image_gallery.models import GalleryItem


def _is_dark() -> bool:
    """Theme darkness (Rule A: bare manager defaults to light)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        return bool(ThemeManager.get_instance().is_dark())
    except Exception:
        return False


def _list_token(token: str, fallback_hex: str) -> QColor:
    """Resolve a ThemeManager token; hex-string fallback (contract-clean)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    return QColor(fallback_hex)


def _action_colors() -> tuple[QColor, QColor, QColor, QColor]:
    """Tri-color chrome glyphs + danger base (gold/red/accent/red)."""
    dark = _is_dark()
    gold = _list_token("gallery.status.warn", "#e8b64c" if dark else "#b77900")
    red = _list_token("gallery.status.danger", "#D93025" if dark else "#c0392b")
    accent = _list_token("gallery.accent.bar", "#0096FF" if dark else "#0078D4")
    return gold, red, accent, red


def _apply_list_rejected_visuals(card: Button, item: GalleryItem) -> None:
    """Rejected = dim wash + strike-through. No pills, no outline, no corner switch.

    List rows are borderless capsules (palette parity): rank/leader state is
    inline text (``#N ★``), rejected adds the dim + strike. One edge per
    boundary — no BorderLayer stroke stacked over the fill + pixmap clips
    (docs: sdf-edge-feather-1px, one rasterizer per edge).
    """
    try:
        rejected = bool(getattr(item, "rejected", False))
    except Exception:
        rejected = False
    try:
        card.setBadge(None)
    except Exception:
        pass
    try:
        # A list row never paints the grid pill (it renders the badge inline in
        # its title row), but the per-widget cache must not survive a rebind:
        # the pool never mixes modes today, and this keeps a future row<->
        # grid reuse from resurrecting a stale pill.
        card._gallery_badge = None  # type: ignore[attr-defined]
        card._gallery_badge_style = None  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        card.setBorderColor(None)
    except Exception:
        pass
    try:
        if hasattr(card, "set_show_strike_through"):
            card.set_show_strike_through(bool(rejected))
    except Exception:
        pass
    try:
        card.setEnabled(True)
    except Exception:
        pass
