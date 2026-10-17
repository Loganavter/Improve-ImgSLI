"""Quick look danger-trash icon — red-tinted ``delete`` resolver + lazy handle.

Module → package (plan-gallery-split-2026-10-17, Part C2): moved here verbatim
from ``ui/quick_look/overlay_build.py`` — function names and signatures
unchanged, re-exported by the ``overlay_build`` package for importers/tests.

The toolkit painter draws icon pixmaps verbatim (no foreground tint), so the
monochrome source is recolored with the ``gallery.status.danger`` token at
paint time and cached per ``("delete", is_dark())``.
"""

from __future__ import annotations

from tabs.image_gallery.ui.quick_look.labels_theme import (
    _is_dark_theme,
    _token_color,
)


_DANGER_TRASH_ICON_CACHE: dict[tuple[str, bool, int], object] = {}


def _resolve_danger_trash_icon(fallback_danger=None) -> object:
    """Resolve and tint ``delete`` to the live ``gallery.status.danger`` token (cached)."""
    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        from sli_ui_toolkit.icons import resolve_icon

        dark = _is_dark_theme()
        danger = _token_color(
            "gallery.status.danger", "#c0392b" if not dark else "#d64545"
        )
        if danger is None:
            danger = fallback_danger
        if danger is None:
            return "delete"
        col = danger if isinstance(danger, QColor) else QColor(danger)
        cache_key = ("delete", bool(dark), int(col.rgba()))
        cached = _DANGER_TRASH_ICON_CACHE.get(cache_key)
        if isinstance(cached, QIcon) and not cached.isNull():
            return cached
        base = resolve_icon("delete")
        if base is None or base.isNull():
            return "delete"
        pm = base.pixmap(QSize(64, 64))
        if pm.isNull():
            return "delete"
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
        if out.isNull():
            return "delete"
        icon = QIcon(out)
        if not icon.isNull():
            _DANGER_TRASH_ICON_CACHE[cache_key] = icon
        return icon
    except Exception:
        return "delete"


def _danger_trash_icon(danger=None) -> object:
    """Lazy red-tinted "delete" icon handle for the quick-look Delete button.

    The toolkit painter draws icon pixmaps verbatim (no foreground tint),
    so the monochrome source stays black unless recolored. Fill the
    silhouette with the live ``gallery.status.danger`` token at paint time
    via CompositionMode_SourceIn and cache per ``("delete", is_dark())`` so
    ``icon.cacheKey()`` stays stable within a theme.
    """
    from functools import partial

    from sli_ui_toolkit.icons import lazy_icon

    return lazy_icon(partial(_resolve_danger_trash_icon, danger))
