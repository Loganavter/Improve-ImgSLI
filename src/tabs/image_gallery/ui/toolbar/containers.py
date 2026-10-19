"""Gallery toolbar segmented-switch container widgets (painter-painted, no QSS).

Split out of ``ui/toolbar.py`` (plan-gallery-split-2026-10-17, Part C6);
bodies moved verbatim — ``GalleryToolbar`` keeps the same class in the
package ``__init__``, which re-exports these containers.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px

from .theme import _is_dark_theme


def _subscribe_scale_repaint(widget: QWidget) -> None:
    """Repaint a plain-painted container on a live ``UiScale`` change.

    Both containers paint their rounded rect with ``scaled_px(8)`` at USE time,
    so a factor change only needs a repaint — but nothing repaints them today
    (they subscribe to the theme signal, not the unified metrics bus). The
    corner radius derives from the scale axis only.
    """
    try:
        from sli_ui_toolkit.ui.managers import connect_ui_metrics
        from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE
    except Exception:
        return

    def _on_metrics(*_axes) -> None:
        try:
            widget.update()
        except Exception:
            pass

    try:
        connect_ui_metrics(widget, _on_metrics, axes=frozenset({AXIS_SCALE}))
    except Exception:
        pass


class GalleryToolbarViewSwitchContainer(QWidget):
    """Segmented view-switch background (106×32, r8, painter-painted, no QSS)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        _subscribe_scale_repaint(self)

    def _on_theme_changed(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QColor, QPainter

            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import try_resolve_theme_color

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
                bg = QColor(col) if isinstance(col, str) else col
                if bg is None:
                    # NOTE: was #333333 (dark-only) — now stats-background light/dark chain.
                    bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            except Exception:
                # NOTE: was #333333 (dark-only) — now stats-background light/dark chain.
                bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            try:
                border = try_resolve_theme_color(ThemeManager.get_instance(), "dialog.border")
                border_col = QColor(border) if isinstance(border, str) else border
                if border_col is None:
                    # NOTE: was #4a4a4a (dark-only) — now dialog-border light/dark chain.
                    border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            except Exception:
                # NOTE: was #4a4a4a (dark-only) — now dialog-border light/dark chain.
                border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            p.setPen(border_col)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), scaled_px(8), scaled_px(8))
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class GalleryToolbarDomainSwitchContainer(QWidget):
    """Segmented domain-switch background (Algorithms|AI), painter-painted, no QSS.

    Mirrors ``GalleryToolbarViewSwitchContainer`` — same tokens/shape; only
    the child segments differ (plan-gallery-two-domain-axes W2).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        _subscribe_scale_repaint(self)

    def _on_theme_changed(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QColor, QPainter

            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import try_resolve_theme_color

            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                col = try_resolve_theme_color(ThemeManager.get_instance(), "gallery.stats.background")
                bg = QColor(col) if isinstance(col, str) else col
                if bg is None:
                    bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            except Exception:
                bg = QColor("#8a8a8a" if not _is_dark_theme() else "#3c3c3c")
            try:
                border = try_resolve_theme_color(ThemeManager.get_instance(), "dialog.border")
                border_col = QColor(border) if isinstance(border, str) else border
                if border_col is None:
                    border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            except Exception:
                border_col = QColor("#c0c0c0" if not _is_dark_theme() else "#555555")
            p.setPen(border_col)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), scaled_px(8), scaled_px(8))
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
