"""Quick look histograms — banding comb vs generic bars."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

from PySide6.QtGui import QColor


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


class _BandingCombHistogram(QWidget):
    """Banding: gradient histogram comb spikes = banding steps (sky).

    Container 56px per mockup (spikes reach 50px) — never clip the signature.
    """

    def __init__(self, severity: str = "clean", parent=None) -> None:
        super().__init__(parent)
        self._severity = severity
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(scaled_px(2))
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        base_heights = [18, 24, 30, 34, 36, 34, 30, 24, 18]
        spike_heights = [40, 44, 38, 32] if severity == "flagged" else ([40, 44, 38, 32] if severity == "mild" else [])
        from PySide6.QtGui import QPalette

        base_col = _token_qcolor("surface.button", "#5a5a5a")
        for h in base_heights:
            bar = QWidget(self)
            bar.setFixedSize(scaled_px(9), scaled_px(h))
            pal = bar.palette()
            pal.setColor(QPalette.ColorRole.Window, base_col)
            bar.setAutoFillBackground(True)
            bar.setPalette(pal)
            lay.addWidget(bar)
        if spike_heights:
            if severity == "mild":
                spike_col = _token_qcolor("gallery.status.warn", "#e8b64c")
            else:
                spike_col = _token_qcolor("gallery.status.danger", "#D93025")
            for h in spike_heights[:4]:
                bar = QWidget(self)
                bar.setFixedSize(scaled_px(9), scaled_px(h))
                pal = bar.palette()
                pal.setColor(QPalette.ColorRole.Window, spike_col)
                bar.setAutoFillBackground(True)
                bar.setPalette(pal)
                lay.addWidget(bar)
            if severity == "flagged":
                for h in [46, 50, 42]:
                    bar = QWidget(self)
                    bar.setFixedSize(scaled_px(9), scaled_px(h))
                    pal = bar.palette()
                    pal.setColor(QPalette.ColorRole.Window, _token_qcolor("gallery.status.danger", "#D93025"))
                    bar.setAutoFillBackground(True)
                    bar.setPalette(pal)
                    lay.addWidget(bar)
        self.setFixedHeight(scaled_px(56))
        try:
            from PySide6.QtGui import QPalette

            pal2 = self.palette()
            pal2.setColor(QPalette.ColorRole.Window, _token_qcolor("surface.background", "#262626"))
            self.setAutoFillBackground(True)
            self.setPalette(pal2)
        except Exception:
            pass


class _GenericHistogram(QWidget):
    """Generic artifact mini bars (non-banding)."""

    def __init__(self, severity: str = "clean", parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(scaled_px(2))
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heights = [18, 24, 30, 34, 36, 34, 30, 24, 18]
        from PySide6.QtGui import QPalette

        if severity == "flagged":
            colors = [_token_qcolor("gallery.status.danger", "#D93025")] * len(heights)
        elif severity == "mild":
            colors = [_token_qcolor("gallery.status.warn", "#e8b64c")] * len(heights)
        else:
            colors = [_token_qcolor("surface.button", "#5a5a5a")] * len(heights)
        for h, c in zip(heights, colors):
            bar = QWidget(self)
            bar.setFixedSize(scaled_px(9), scaled_px(h))
            pal = bar.palette()
            pal.setColor(QPalette.ColorRole.Window, c)
            bar.setAutoFillBackground(True)
            bar.setPalette(pal)
            lay.addWidget(bar)
        # P0-9: container fits the tallest bar (mockup 56).
        self.setFixedHeight(scaled_px(56))


class _HistogramStub(QWidget):
    """Backward compat stub routing to banding comb vs generic."""

    def __init__(self, severity: str = "clean", parent=None, artifact: str | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner: QWidget
        if artifact == "banding":
            inner = _BandingCombHistogram(severity=severity, parent=self)
        else:
            inner = _GenericHistogram(severity=severity, parent=self)
        lay.addWidget(inner)
        # P0-9: container fits the tallest bar (mockup 56).
        self.setFixedHeight(scaled_px(56))
