"""Dots helpers — severity tokens & per-dot colors (painter pipeline only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem

# S2-12: colors via ThemeManager tokens per THEMING.md; fallback hex kept for offscreen tests
_SEVERITY_TOKEN_FALLBACKS: dict[str, tuple[str, str]] = {
    "clean": ("gallery.status.ok", "#3fbf5f"),
    "mild": ("gallery.status.warn", "#e8b64c"),
    "flagged": ("gallery.status.danger", "#D93025"),
}
# Light-theme counterparts of the dark fallbacks above (themes.json light section).
_SEVERITY_FALLBACKS_LIGHT: dict[str, str] = {
    "clean": "#2e7d32",
    "mild": "#b77900",
    "flagged": "#c0392b",
}
_ERROR_LINE_TOKEN_FALLBACK = ("gallery.status.danger", "#D93025")
_ERROR_LINE_FALLBACK_LIGHT = "#c0392b"
_ACCENT_TOKEN_FALLBACK = ("gallery.accent.bar", "#0096FF")
_ACCENT_FALLBACK_LIGHT = "#0078D4"

_DOTS_TEXT = "● ● ●"
_DOTS_ROW_GAP = 2  # RowsContent.row_gap default (compact layout)


def _is_dark() -> bool:
    """Current theme darkness for fallback selection (Rule A).

    Keyed ONLY on ``ThemeManager.is_dark()``: a bare manager defaults to
    ``_current_theme='light'`` (``is_dark()`` False), and an
    empty/unregistered palette does NOT imply dark. Callers
    (``stats_strip``, ``grid_view``, ``hover``) delegate here, so every
    ``_fallback_for(light, dark)`` pair resolves light under a bare manager —
    same as the ``_is_dark_theme`` chains in ``toolbar``/``quick_look``.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        return bool(ThemeManager.get_instance().is_dark())
    except Exception:
        # Manager unreachable (no Qt host at all) — mirror the bare-manager
        # default, which is the light theme.
        return False


def _token_color(token: str, fallback_hex: str):
    """Resolve a ThemeManager palette token; fall back when absent."""
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        resolved = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if resolved is not None:
            # resolved may be QColor or hex string — normalize to QColor
            return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(fallback_hex)


def _severity_color(sev: str):
    key = (sev or "clean").lower()
    token, dark_fallback = _SEVERITY_TOKEN_FALLBACKS.get(key, _SEVERITY_TOKEN_FALLBACKS["clean"])
    fallback = dark_fallback if _is_dark() else _SEVERITY_FALLBACKS_LIGHT.get(key, dark_fallback)
    return _token_color(token, fallback)


def _error_line_color():
    """Rejected/error line: ``gallery.status.danger`` → light/dark fallback."""
    token, dark_fallback = _ERROR_LINE_TOKEN_FALLBACK
    fallback = dark_fallback if _is_dark() else _ERROR_LINE_FALLBACK_LIGHT
    return _token_color(token, fallback)


def _accent_color():
    """Badge/underline accent with the frozen chain + light/dark fallback.

    ``gallery.accent.bar`` → ``accent`` → ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for tok in ("gallery.accent.bar", "accent"):
            resolved = try_resolve_theme_color(mgr, tok)
            if resolved is not None:
                return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(_ACCENT_TOKEN_FALLBACK[1] if _is_dark() else _ACCENT_FALLBACK_LIGHT)


def _dots_for_item(
    item: GalleryItem, mode: object = None, domain: object = None
) -> tuple[str, tuple[object, ...]]:
    """Stage 2: per-dot three quality dots via artifact severities (design.md:67-83).

    Severities + mode mapping come from the single source of truth
    (``use_cases/quality.py``); the *domain* picks the read
    (``services/quality_read``): AI = the VLM's reported defects, Algorithms =
    the local detector severities. Here only severity→color stays.
    Each dot color resolves via theme tokens (S2-12): clean→success,
    mild→warning, flagged→danger (fallback hexes kept for offscreen tests).
    Returns ``(dot_text, tuple[QColor, QColor, QColor])`` for the dots row.
    """

    dot_text = _DOTS_TEXT

    def _color_for_severity(s: str):
        s = (s or "clean").lower()
        if s == "flagged":
            return _severity_color("flagged")
        if s == "mild":
            return _severity_color("mild")
        return _severity_color("clean")

    try:
        from tabs.image_gallery.services import quality_read as _quality_read
        from tabs.image_gallery.use_cases import quality as _quality

        artifacts = _quality.MODE_ARTIFACTS[_quality.normalize_mode(mode)]
        triplet = tuple(
            _quality_read.domain_artifact_severity(item, aid, domain=domain)
            for aid in artifacts
        )
    except Exception:
        triplet = ("clean", "clean", "clean")
    return dot_text, tuple(_color_for_severity(s) for s in triplet)
