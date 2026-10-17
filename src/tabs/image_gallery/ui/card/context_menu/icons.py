"""Monochrome menu-icon resolution for the gallery card context menu.

Split out of ``ui/card/context_menu.py`` per the module→package split
(``plan-gallery-split-2026-10-17``); function names/bodies moved verbatim.
"""

from __future__ import annotations

_MENU_ICON_CACHE: dict[tuple[object, bool, int], object] = {}


def _resolve_menu_icon(name):  # type: ignore[no-untyped-def]
    """Resolve *name* for the live theme and tint to ``dialog.text`` (cached)."""
    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        from sli_ui_toolkit.icons import resolve_icon
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        dark = bool(mgr.is_dark())
        c = try_resolve_theme_color(mgr, "dialog.text")
        if c is None:
            return name
        col = c if isinstance(c, QColor) else QColor(c)
        cache_key = (name, dark, int(col.rgba()))
        cached = _MENU_ICON_CACHE.get(cache_key)
        if isinstance(cached, QIcon) and not cached.isNull():
            return cached
        base = resolve_icon(name)
        if base is None or base.isNull():
            return name
        pm = base.pixmap(QSize(64, 64))
        if pm.isNull():
            return name
        out = QPixmap(pm.size())
        try:
            out.setDevicePixelRatio(pm.devicePixelRatio())
        except Exception:
            pass
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            painter.drawPixmap(0, 0, pm)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(out.rect(), col)
        finally:
            painter.end()
        icon = QIcon(out)
        if not icon.isNull():
            _MENU_ICON_CACHE[cache_key] = icon
        return icon
    except Exception:
        return name


def _menu_icon(name):  # type: ignore[no-untyped-def]
    """Return a lazy menu-icon handle tinted to the row-text theme color.

    The toolkit paints ``ContextMenuAction.icon`` verbatim, so icons from
    mixed sources (brand-blue ``ai.svg``, black ``compare.svg``, white
    ``delete``/``star``/``check``) rendered as a rainbow in one menu. Tinting
    them all to ``dialog.text`` — the same color the row paints its label with
    — makes the menu one monochrome family that tracks the theme. Resolved at
    paint time via ``lazy_icon`` and cached per ``(name, is_dark())`` so the
    provider returns a stable ``QIcon``.
    """
    from functools import partial

    from sli_ui_toolkit.icons import lazy_icon

    return lazy_icon(partial(_resolve_menu_icon, name))
