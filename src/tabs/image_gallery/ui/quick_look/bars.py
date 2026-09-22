"""Quick look bars — QWidget bar widgets with painter palette (no QSS)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.managers import scaled_px


def _token_qcolor(token: str, fallback_hex: str) -> QColor:
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
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    return QColor(*fallback_rgba)


def dual_marker_frac(hf_ratio: float) -> float:
    """Marker fraction on the restored↔invented axis for an HF ratio.

    ``frac = 0.5 - clamp(hf,-1,1)*0.5`` — positive gain (plausible detail)
    leans the marker onto the restored (left) side, so ``+0.18 → 0.41``
    per ``design/ui-mockup-v4-quicklook.svg``. Pure (unit-testable).
    """
    try:
        hf = max(-1.0, min(1.0, float(hf_ratio)))
    except Exception:
        return 0.5
    return 0.5 - hf * 0.5


class _BarWidget(QWidget):
    """Simple horizontal bar: background + fill fraction."""

    def __init__(self, fraction: float = 0.0, fill_color=None, parent=None) -> None:
        super().__init__(parent)
        self._fraction = max(0.0, min(1.0, float(fraction)))
        self._fill_color = fill_color
        self.setFixedHeight(scaled_px(6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._fill = QWidget(self)
        self._fill.setObjectName("QuickLookBarFill")
        try:
            from PySide6.QtGui import QPalette

            pal = self._fill.palette()
            col = fill_color if fill_color is not None else _token_qcolor("gallery.status.ok", "#3fbf5f")
            pal.setColor(QPalette.ColorRole.Window, col)
            self._fill.setAutoFillBackground(True)
            self._fill.setPalette(pal)
            pal2 = self.palette()
            pal2.setColor(QPalette.ColorRole.Window, _token_qcolor("flyout.border", "#4a4a4a"))
            self.setAutoFillBackground(True)
            self.setPalette(pal2)
        except Exception:
            pass
        outer.addWidget(self._fill, 0)
        outer.addStretch(1)
        self._update_fill()

    def _update_fill(self) -> None:
        try:
            layout = self.layout()
            if layout is not None and layout.count() >= 2:
                pass
        except Exception:
            pass
        try:
            pw = self.width()
            if pw > 0:
                fw = int(pw * self._fraction)
                self._fill.setFixedWidth(max(scaled_px(4), fw))
            else:
                pass
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            pw = self.width()
            fw = int(pw * self._fraction) if pw > 0 else scaled_px(40)
            self._fill.setFixedWidth(max(scaled_px(4), fw))
        except Exception:
            pass


class _DualRestoredInventedBar(QWidget):
    """Detail gain dual scale: restored (green) ↔ invented (red) via ThemeManager.

    Fidelity mode HF ratio: center = 0 (0.5 fraction). Left segment = restored,
    right segment = invented. Marker position encodes hf_ratio.
    """

    def __init__(self, hf_ratio: float = 0.18, parent=None) -> None:
        super().__init__(parent)
        self._hf = float(hf_ratio)
        self.setFixedHeight(scaled_px(6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        try:
            from PySide6.QtGui import QPalette

            pal2 = self.palette()
            bg = _token_qcolor("quick_look.bar.background", "#262626")
            # If token resolved is not None, use it; else fallback already is resolved
            pal2.setColor(QPalette.ColorRole.Window, bg)  # type: ignore[arg-type]
            self.setAutoFillBackground(True)
            self.setPalette(pal2)
        except Exception:
            try:
                from PySide6.QtGui import QPalette

                pal2 = self.palette()
                pal2.setColor(QPalette.ColorRole.Window, _token_qcolor("quick_look.bar.background", "#262626"))
                self.setAutoFillBackground(True)
                self.setPalette(pal2)
            except Exception:
                pass
        self._left = QWidget(self)
        self._left.setObjectName("DualBarLeft")
        self._right = QWidget(self)
        self._right.setObjectName("DualBarRight")
        try:
            from PySide6.QtGui import QPalette

            # left restored - gallery.status.ok with alpha 140
            left_base = _token_qcolor("gallery.status.ok", "#3fbf5f")
            try:
                left_base.setAlpha(140)
            except Exception:
                pass
            pal_l = self._left.palette()
            pal_l.setColor(QPalette.ColorRole.Window, left_base)
            self._left.setAutoFillBackground(True)
            self._left.setPalette(pal_l)
            # right invented - gallery.status.danger with alpha 115
            right_base = _token_qcolor("gallery.status.danger", "#D93025")
            try:
                right_base.setAlpha(115)
            except Exception:
                pass
            pal_r = self._right.palette()
            pal_r.setColor(QPalette.ColorRole.Window, right_base)
            self._right.setAutoFillBackground(True)
            self._right.setPalette(pal_r)
        except Exception:
            pass
        outer.addWidget(self._left, 0)
        outer.addWidget(self._right, 0)
        outer.addStretch(1)
        self._update_geometry()

    def _update_geometry(self) -> None:
        try:
            frac = dual_marker_frac(self._hf)
            pw = self.width()
            if pw <= 0:
                pw = scaled_px(296)
            total = pw
            marker_x = int(total * frac)
            left_w = max(scaled_px(4), marker_x)
            right_w = max(0, total - marker_x)
            self._left.setFixedWidth(left_w)
            self._right.setFixedWidth(right_w)
        except Exception:
            pass

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_geometry()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        try:
            from PySide6.QtGui import QPainter, QBrush

            frac = dual_marker_frac(self._hf)
            cx = int(self.width() * frac)
            cy = self.height() // 2
            r = scaled_px(5)
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            dot_col = _token_qcolor("button.primary.text", "#ffffff")
            p.setBrush(QBrush(dot_col))
            p.setPen(dot_col)
            p.drawEllipse(cx - r // 2, cy - r // 2, r, r)
            p.end()
        except Exception:
            pass
