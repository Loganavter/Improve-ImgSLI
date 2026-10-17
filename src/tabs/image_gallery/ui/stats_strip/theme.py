"""Stats-strip theme helpers — token resolvers + light/dark fallbacks.

Split out of ``ui/stats_strip.py`` (plan-gallery-split-2026-10-17, Part C6);
bodies moved verbatim. ``StatsStrip`` keeps the same class in the package
``__init__``, which re-exports every helper for existing importers/tests.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# -- theme helpers (sanctioned wrapper only) ----------------------------------

def _is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True


def _fallback_for(light: str, dark: str) -> str:
    """Pick the theme-appropriate fallback hex (no dark-only defaults)."""
    try:
        return dark if _is_dark() else light
    except Exception:
        return dark

def _token_qcolor(token: str, fallback_hex: str) -> QColor:
    """Resolve *token* via ``try_resolve_theme_color`` with *fallback_hex*."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if col is not None:
            if isinstance(col, QColor):
                return col
            return QColor(col)
    except Exception:
        pass
    return QColor(fallback_hex)


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor:
    """Resolve *token* via wrapper; fallback to rgba tuple (e.g. input.border.thin)."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if col is not None:
            if isinstance(col, QColor):
                return col
            return QColor(col)
    except Exception:
        pass
    return QColor(*fallback_rgba)


def _accent_color() -> QColor:
    """Accent resolved through the theme token chain (no hand-color).

    Chain (frozen seam): ``accent`` token → ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    return _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))


def _accent_soft_color() -> QColor:
    """Enabled clean button text — accent lighter (≈ #7fc4ff)."""
    base = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
    try:
        # lighter(150) approximates #7fc4ff from #0096FF
        c = QColor(base)
        return c.lighter(150)
    except Exception:
        pass
    return _token_qcolor("accent", "#7fc4ff")


def _stats_text_color() -> QColor:
    """Stats body text: ``gallery.stats.text`` → light/dark fallback."""
    return _token_qcolor("gallery.stats.text", _fallback_for("#1f1f1f", "#dfdfdf"))


def _header_text_color() -> QColor:
    """Dim header text: ``gallery.header.text`` → light/dark fallback."""
    return _token_qcolor("gallery.header.text", _fallback_for("#434343", "#9a9a9a"))


def _flyout_border_color() -> QColor:
    """Subtle border: ``flyout.border`` → light/dark fallback."""
    return _token_qcolor("flyout.border", _fallback_for("#e0e0e0", "#4a4a4a"))


def _thin_border_color() -> QColor:
    """Hairline border: ``input.border.thin`` → per-theme rgba fallback."""
    if _is_dark():
        return _token_rgba_qcolor("input.border.thin", (255, 255, 255, 60))
    return _token_rgba_qcolor("input.border.thin", (0, 0, 0, 45))


def _stats_bg_color() -> QColor:
    """Stats bar surface: ``gallery.stats.background`` → light/dark fallback.

    NOTE: the historical dark-only ``#333333`` default is kept for the dark
    theme only; the light theme falls back to the registered ``#8a8a8a``.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
        if col is not None:
            return col if isinstance(col, QColor) else QColor(col)
    except Exception:
        pass
    if _is_dark():
        return QColor(0x33, 0x33, 0x33)
    return QColor("#8a8a8a")


def _stats_border_color() -> QColor:
    """Stats strip edge: ``gallery.card.border`` → ``flyout.border`` → theme-aware fallback.

    Mockup (v2-light): stats strip is a #ffffff card with a 1px #e2e4e8 edge —
    same hairline as gallery cards. Frozen seam: ``try_resolve_theme_color`` only.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for _tok in ("gallery.card.border", "flyout.border"):
            try:
                col = try_resolve_theme_color(mgr, _tok)
            except Exception:
                col = None
            if col is not None:
                return col if isinstance(col, QColor) else QColor(col)
    except Exception:
        pass
    if _is_dark():
        return QColor(255, 255, 255, 30)
    return QColor("#e2e4e8")


def _accent_border_color() -> QColor:
    """Enabled clean button border — accent with 60% opacity (alpha 153)."""
    base = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
    try:
        c = QColor(base)
        c.setAlpha(153)
        return c
    except Exception:
        pass
    # fallback — ensure alpha applied
    try:
        fallback = _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
        c2 = QColor(fallback)
        c2.setAlpha(153)
        return c2
    except Exception:
        pass
    return _token_qcolor("accent", _fallback_for("#0078D4", "#0096FF"))
