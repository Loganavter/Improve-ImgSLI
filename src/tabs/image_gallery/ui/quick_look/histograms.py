"""Quick look histograms — banding comb vs generic bars."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px

from tabs.image_gallery.ui.quick_look.bars import (
    _FillBlock,
    _connect_theme_refresh,
    _token_qcolor,
)


def _severity_fill(severity: str) -> QColor:
    """Severity color via the single card-dots mapping (frozen seam).

    Reuses ``ui/card/dots.py::_severity_color`` — no second severity mapping
    lives here; the except path falls back to a neutral surface tone, never a
    competing severity claim.
    """
    try:
        from tabs.image_gallery.ui.card.dots import _severity_color

        return _severity_color(severity)
    except Exception:
        pass
    return _token_qcolor("surface.button", "#8a8a8a", "#5a5a5a")


def _base_fill() -> QColor:
    return _token_qcolor("surface.button", "#8a8a8a", "#5a5a5a")


def _container_bg() -> QColor:
    # Fallbacks track the REAL token values (surface.background light is
    # #ffffff again after the 2026-09-23 gallery-only substrate rescope).
    return _token_qcolor("surface.background", "#ffffff", "#2b2b2b")


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
        self._bg_color = _container_bg()
        self._bars: list[tuple[_FillBlock, str]] = []
        base_heights = [18, 24, 30, 34, 36, 34, 30, 24, 18]
        spike_heights = [40, 44, 38, 32] if severity == "flagged" else ([40, 44, 38, 32] if severity == "mild" else [])

        base_col = _base_fill()
        for h in base_heights:
            bar = _FillBlock(base_col, self)
            bar.setFixedSize(scaled_px(9), scaled_px(h))
            lay.addWidget(bar)
            self._bars.append((bar, "base"))
        if spike_heights:
            spike_col = _severity_fill(severity)
            for h in spike_heights[:4]:
                bar = _FillBlock(spike_col, self)
                bar.setFixedSize(scaled_px(9), scaled_px(h))
                lay.addWidget(bar)
                self._bars.append((bar, "sev"))
            if severity == "flagged":
                for h in [46, 50, 42]:
                    bar = _FillBlock(_severity_fill(severity), self)
                    bar.setFixedSize(scaled_px(9), scaled_px(h))
                    lay.addWidget(bar)
                    self._bars.append((bar, "sev"))
        self.setFixedHeight(scaled_px(56))
        _connect_theme_refresh(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        try:
            self._bg_color = _container_bg()
        except Exception:
            pass
        try:
            base_col = _base_fill()
            sev_col = _severity_fill(self._severity)
            for bar, kind in self._bars:
                try:
                    bar.set_fill_color(base_col if kind == "base" else sev_col)
                except Exception:
                    pass
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
            p.fillRect(self.rect(), self._bg_color)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class _GenericHistogram(QWidget):
    """Generic artifact mini bars (non-banding)."""

    def __init__(self, severity: str = "clean", parent=None) -> None:
        super().__init__(parent)
        self._severity = severity
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(scaled_px(2))
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heights = [18, 24, 30, 34, 36, 34, 30, 24, 18]
        self._bg_color = _container_bg()
        self._bars: list[tuple[_FillBlock, str]] = []

        if severity in ("flagged", "mild"):
            sev_col = _severity_fill(severity)
            colors = [sev_col] * len(heights)
            kinds = ["sev"] * len(heights)
        else:
            base_col = _base_fill()
            colors = [base_col] * len(heights)
            kinds = ["base"] * len(heights)
        for h, c, k in zip(heights, colors, kinds):
            bar = _FillBlock(c, self)
            bar.setFixedSize(scaled_px(9), scaled_px(h))
            lay.addWidget(bar)
            self._bars.append((bar, k))
        # P0-9: container fits the tallest bar (mockup 56).
        self.setFixedHeight(scaled_px(56))
        _connect_theme_refresh(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        try:
            self._bg_color = _container_bg()
        except Exception:
            pass
        try:
            if self._severity in ("flagged", "mild"):
                col = _severity_fill(self._severity)
            else:
                col = _base_fill()
            for bar, _kind in self._bars:
                try:
                    bar.set_fill_color(col)
                except Exception:
                    pass
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
            p.fillRect(self.rect(), self._bg_color)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


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
