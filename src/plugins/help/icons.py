"""Resolve help hub/page icons from the app pack + tree-contributed resolvers.

This is the single choke point for every icon rendered by the in-app Help
(``sidebar``/search rows, hub cards, page leading icons). Every icon that
leaves here is **monochrome**: the resolved source is used as an alpha mask
and filled with one theme colour, so a coloured SVG in the app pack (e.g.
``highlight_diff_icon.svg``) still reads as help chrome instead of a splash
of its own hue.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ui.icon_manager import AppIcon, get_app_icon

IconResolver = Callable[[str], QIcon | None]

#: Existing theme text tokens that read on both themes (#1f1f1f light /
#: #dfdfdf dark — see ``resources/themes.json``). Help lives in a dialog, so
#: its icons should match the dialog's text colour; the later tokens are
#: palette-standard fallbacks, never hardcoded RGB.
_ICON_COLOR_TOKENS = ("dialog.text", "Text", "WindowText")

#: Raster target for sources that declare no sizes (SVG). Mirrors the toolkit's
#: themed-icon pipeline so help icons stay as crisp as ordinary toolbar icons.
_SVG_RASTER_PX = 256

# Monochrome results keyed by (name, colour, ui-scale). The colour component is
# what makes a theme switch self-invalidating: a new theme resolves a different
# ``_ICON_COLOR_TOKENS`` value, so the next ``resolve_help_icon`` misses the
# stale tint instead of serving the previous theme's colour. The scale component
# keeps HiDPI/interface-scale changes from serving an under-resolved raster.
# Nothing is cached while no theme colour resolves, so a later themed resolve
# cannot be served a stale un-tinted source.
_cache: dict[tuple[str, int, float], QIcon] = {}
_theme_hook_installed = False


def clear_help_icon_cache() -> None:
    """Drop cached monochrome icons (theme swap, icon-pack reload, tests)."""
    _cache.clear()


def _ui_scale_key() -> float:
    try:
        from sli_ui_toolkit.managers import UiScale

        return UiScale.get_instance().factor()
    except Exception:
        return 1.0


def _theme_icon_color() -> QColor:
    """Resolve the monochrome fill from ThemeManager (never hardcoded).

    Returns an invalid colour when no token resolves (un-themed host) so
    callers fall back to the source icon instead of inventing a value.
    """
    try:
        from sli_ui_toolkit.theme import ThemeManager

        from ui.theming import try_resolve_theme_color

        manager = ThemeManager.get_instance()
        for token in _ICON_COLOR_TOKENS:
            color = try_resolve_theme_color(manager, token)
            if color is not None and color.isValid():
                return color
    except Exception:
        pass
    return QColor()


def _ensure_theme_hook() -> None:
    """Clear the cache whenever the theme changes, so no stale colour lingers."""
    global _theme_hook_installed
    if _theme_hook_installed:
        return
    try:
        from sli_ui_toolkit.theme import ThemeManager

        ThemeManager.get_instance().theme_changed.connect(clear_help_icon_cache)
    except Exception:
        return  # retry on the next resolve
    _theme_hook_installed = True


def _mask_pixmap(source: QPixmap, color: QColor) -> QPixmap:
    """Return *source*'s alpha silhouette filled with *color*."""
    masked = QPixmap(source.size())
    masked.fill(Qt.GlobalColor.transparent)
    painter = QPainter(masked)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(masked.rect(), color)
    painter.end()
    return masked


def _monochrome(icon: QIcon, color: QColor) -> QIcon:
    """Alpha-mask *icon* into a single *color*; return *icon* if impossible."""
    if icon.isNull() or not color.isValid():
        return icon
    sizes = [size for size in icon.availableSizes() if size.isValid()]
    if not sizes:
        sizes = [QSize(_SVG_RASTER_PX, _SVG_RASTER_PX)]
    result = QIcon()
    for size in sizes:
        source = icon.pixmap(size)
        if source.isNull():
            continue
        result.addPixmap(_mask_pixmap(source, color))
    return result if not result.isNull() else icon


def _resolve_source(
    name: str | None,
    resolvers: Iterable[IconResolver] | None,
) -> QIcon:
    if not name:
        return get_app_icon(AppIcon.HELP)
    icon = get_app_icon(name)
    if not icon.isNull():
        return icon
    for resolver in resolvers or ():
        try:
            found = resolver(name)
        except Exception:
            continue
        if found is not None and not found.isNull():
            return found
    return get_app_icon(AppIcon.HELP)


def resolve_help_icon(
    name: str | None,
    *,
    resolvers: Iterable[IconResolver] | None = None,
) -> QIcon:
    _ensure_theme_hook()
    color = _theme_icon_color()
    if not color.isValid():
        # No theme token to tint from — hand back the source rather than
        # inventing a colour, and do not cache the un-tinted result.
        return _resolve_source(name, resolvers)
    cache_key = (name or "\x00fallback", color.rgba(), _ui_scale_key())
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    tinted = _monochrome(_resolve_source(name, resolvers), color)
    _cache[cache_key] = tinted
    return tinted
