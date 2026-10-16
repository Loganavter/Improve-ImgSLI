"""Gallery toolbar theme helpers — accent fill-chip + dark-theme resolution.

Split out of ``ui/toolbar.py`` (plan-gallery-split-2026-10-17, Part C6);
bodies moved verbatim.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

def _is_dark_theme() -> bool:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        inst = ThemeManager.get_instance()
        try:
            return bool(inst.is_dark())
        except Exception:
            pass
        try:
            return str(inst.get_current_theme()).lower() != "light"
        except Exception:
            pass
    except Exception:
        pass
    return True


def _resolve_toolbar_accent_fill(alpha: int = 51) -> QColor:
    """S2 mockup x1130 y74: active view segment is a fill-chip (blue 0.2), not a border."""
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color
        for token in ("gallery.accent.bar", "accent"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), token)
            if c is not None:
                col = QColor(c) if isinstance(c, str) else QColor(c)
                try: col.setAlpha(int(alpha))
                except Exception: pass
                return col
    except Exception: pass
    # NOTE: was (0,150,255) at alpha (dark-only rgba) — now accent light/dark chain.
    col = QColor("#0078D4" if not _is_dark_theme() else "#0096FF")
    try:
        col.setAlpha(int(alpha))
    except Exception:
        pass
    return col


def _apply_view_fill_chip(active_btn, inactive_btn) -> None:
    """Active segment = accent fill-chip; inactive = transparent (no border)."""
    try:
        active_btn.set_override_bg_color(_resolve_toolbar_accent_fill())
    except Exception:
        pass
    try:
        inactive_btn.set_override_bg_color(None)
    except Exception:
        pass
    try:
        active_btn.setBorderColor(QColor(0, 0, 0, 0))
        inactive_btn.setBorderColor(QColor(0, 0, 0, 0))
    except Exception:
        pass
