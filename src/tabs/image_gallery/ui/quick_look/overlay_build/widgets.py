"""Quick look overlay chrome widgets — painted plate/pill/rule (no QSS).

Module → package (plan-gallery-split-2026-10-17, Part C2): the three painted
chrome widgets (``_AccentPillHost`` / ``_CardPlate`` / ``_RuleWidget``) moved
here verbatim from ``ui/quick_look/overlay_build.py`` — class names and
signatures unchanged, re-exported by the ``overlay_build`` package for
importers and tests.

Painter pipeline owns all visuals — explicit ``paintEvent``, theme-subscribed;
no QSS, no palette.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from tabs.image_gallery.ui.quick_look.labels_theme import (
    _is_dark_theme,
    _token_color,
)


class _AccentPillHost(QWidget):
    """Pill backdrop behind small header chips (explicit paint, no palette).

    ``fill="accent"`` (default): accent-tinted translucent pill (mode chip).
    ``fill="white"``: opaque white pill for dark-on-light chips
    (SHARPNESS CROP) — white in both themes by design; a future theme may
    define the ``gallery.pill.background`` token to take over.
    """

    def __init__(self, parent=None, *, fill: str = "accent") -> None:
        super().__init__(parent)
        self._fill = fill
        self._bg = self._resolve_bg(fill)
        self._border = self._resolve_border(fill)
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_bg(fill: str = "accent") -> QColor:
        if fill == "white":
            col = _token_color("gallery.pill.background", "#ffffff")
            if col is None:
                col = QColor(Qt.GlobalColor.white)
            try:
                col.setAlpha(255)
            except Exception:
                pass
            return col
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            for token in ("gallery.accent.bar", "accent"):
                c = try_resolve_theme_color(ThemeManager.get_instance(), token)
                if c is not None:
                    # QColor(...) copy: never setAlpha a manager-owned instance in place.
                    col = QColor(c) if isinstance(c, str) else QColor(c)
                    try:
                        if col.alpha() == 255:
                            col.setAlpha(51)
                    except Exception:
                        pass
                    return col
        except Exception:
            pass
        # NOTE: was (0,150,255) at alpha 51 (dark-only rgba) — now accent light/dark chain.
        fallback = QColor("#0078D4" if not _is_dark_theme() else "#0096FF")
        try:
            fallback.setAlpha(51)
        except Exception:
            pass
        return fallback

    def _on_theme_changed(self) -> None:
        try:
            self._bg = self._resolve_bg(self._fill)
        except Exception:
            pass
        try:
            self._border = self._resolve_border(self._fill)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    @staticmethod
    def _resolve_border(fill: str = "accent"):
        """Hairline for white pills: opaque white is invisible on the light
        card, so white capsules get a 1px separator border (both themes).
        Accent pills already read via their tint — no border."""
        if fill != "white":
            return None
        try:
            return _token_color("separator.color", "#e5e5e5")
        except Exception:
            return None

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPen
            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._bg)
                p.drawRoundedRect(self.rect(), scaled_px(8), scaled_px(8))
                try:
                    border = getattr(self, "_border", None)
                except Exception:
                    border = None
                if border is not None:
                    half = max(1.0, scaled_px(1)) / 2.0
                    p.setPen(QPen(border, max(1.0, scaled_px(1))))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(QRectF(self.rect()).adjusted(half, half, -half, -half), scaled_px(8), scaled_px(8))
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


# S4 v2 LIGHT (svg:31): 1040x620 card plate — card fill + 1px border + rx 12.
QUICK_LOOK_CARD_RADIUS_PX = 12


class _CardPlate(QWidget):
    """Quick look card plate — ``gallery.panel.background`` fill + border, rx 12.

    Painter pipeline owns visuals (explicit paintEvent, theme-subscribed);
    no QSS, no palette. The plate shares the scroll-host panel token
    (``labels_theme._apply_panel_background``) so the whole overlay is ONE
    flat surface — dark mockup svg:31 pins the plate at ``#303030``, not the
    grid-card ``#383838`` (that one is for grid cards).
    All QColor() calls take resolved variables — never literals
    (contracts/test_no_hardcoded_qcolor.py baseline).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bg = self._resolve_bg()
        self._border = self._resolve_border()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_bg():
        # Overlay surface token first (dark mockup svg:31 / clean-review
        # svg:42): plate and scroll-host panels resolve the SAME token, so no
        # recess seam shows on the flat plate. ``gallery.card.background``
        # (dark #383838) stays the fallback for grid cards only.
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.panel.background", "gallery.card.background", "surface.list", "surface.background"):
                c = try_resolve_theme_color(mgr, token)
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color(
            "gallery.panel.background", "#ffffff" if not _is_dark_theme() else "#303030"
        )

    @staticmethod
    def _resolve_border():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            mgr = ThemeManager.get_instance()
            for token in ("gallery.card.border", "flyout.border"):
                try:
                    c = try_resolve_theme_color(mgr, token)
                except Exception:
                    c = None
                if c is not None:
                    return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color(
            "gallery.card.border", "#e2e4e8" if not _is_dark_theme() else "#4a4a4a"
        )

    def _on_theme_changed(self) -> None:
        try:
            self._bg = self._resolve_bg()
        except Exception:
            pass
        try:
            self._border = self._resolve_border()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPen

            from sli_ui_toolkit.managers import scaled_px

            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                r = QRectF(self.rect())
                rx = scaled_px(QUICK_LOOK_CARD_RADIUS_PX)
                p.setPen(Qt.PenStyle.NoPen)
                try:
                    bg = self._bg
                except Exception:
                    bg = self._resolve_bg()
                p.setBrush(bg)
                p.drawRoundedRect(r, rx, rx)
                try:
                    border = self._border
                except Exception:
                    border = self._resolve_border()
                try:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(border, 1))
                    # Border fully inside the widget rect (not straddling):
                    # the outer half of a straddled 1px pen is clipped and
                    # its AA fade makes the visible line sit ~1px off the
                    # hit-band boundary. Experimental, revert if worse.
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rx, rx)
                except Exception:
                    pass
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class _RuleWidget(QWidget):
    """1px horizontal rule — file-local painted divider (W4 item 3).

    The toolkit ``Divider`` is a button-region dataclass, not a widget
    (``TypeError`` on ``parent=``), and there is no toolkit divider widget
    (``DividerLayer`` is a painter layer, not a ``QWidget``). So the three
    quick-look section rules live here: explicit paintEvent with the
    ``separator.color`` token, theme-subscribed. No QSS.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from sli_ui_toolkit.managers import scaled_px

        # 1px rule + 7px breathing room (was 9): the readability sweep
        # (11px labels) leaves the right column exactly 1px over the
        # viewport — this absorbs it without touching content metrics.
        self.setFixedHeight(scaled_px(8))
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self._color = self._resolve_color()
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    @staticmethod
    def _resolve_color():
        try:
            from sli_ui_toolkit.managers import ThemeManager

            from ui.theming import try_resolve_theme_color

            c = try_resolve_theme_color(ThemeManager.get_instance(), "separator.color")
            if c is not None:
                return c if isinstance(c, QColor) else QColor(c)
        except Exception:
            pass
        return _token_color("separator.color", "#e5e5e5")

    def _on_theme_changed(self) -> None:
        try:
            self._color = self._resolve_color()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            p = QPainter(self)
            try:
                r = self.rect()
                p.fillRect(0, r.height() // 2, r.width(), 1, self._color)
            finally:
                p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
