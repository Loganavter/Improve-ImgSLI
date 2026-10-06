"""The MainWindow RHI primer must be *able* to paint (promotion precondition).

``QRhiWidget::ensureRhi()`` (which promotes the top-level backingstore from
``RasterSurface`` to an RHI-capable type) runs from the paint path. A hidden
widget never receives paint events, so a hidden primer can never prime —
this is the mechanism behind ``inv-2026-10-06-ql-rhi-menu-first`` Timeline #5
("Primer audit") and the reason ``ensure_window_rhi()`` must show its 1x1
primer (which self-destructs on ``firstFrameRendered``) instead of hiding it.
"""

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

from ui.canvas_infra.rhi.rhi_backend import ensure_window_rhi


class _PaintCounter(QRhiWidget):
    """QRhiWidget that counts paint events without touching the RHI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paint_count = 0

    def paintEvent(self, event):  # noqa: N802
        self.paint_count += 1
        # Deliberately NOT calling super(): no RHI attempt, just the
        # delivery proof (hidden widgets get no delivery at all).


def _drain():
    QApplication.processEvents()


def test_hidden_qrhi_widget_receives_no_paint_events(qapp):
    window = QWidget()
    counter = _PaintCounter(window)
    counter.setGeometry(0, 0, 1, 1)
    counter.hide()
    window.show()
    _drain()
    try:
        counter.update()
        _drain()
        assert counter.paint_count == 0
    finally:
        window.close()


def test_shown_qrhi_widget_receives_paint_events(qapp):
    window = QWidget()
    counter = _PaintCounter(window)
    counter.setGeometry(0, 0, 1, 1)
    window.show()
    counter.show()
    _drain()
    try:
        assert counter.paint_count >= 1
    finally:
        window.close()


def test_primer_is_shown_not_hidden(qapp):
    """The primer must not carry an explicit hide: hidden == never primes."""
    window = QWidget()
    try:
        ensure_window_rhi(window)
        primer = window.findChild(QRhiWidget, "rhi_surface_primer")
        assert primer is not None
        assert not primer.isHidden(), "primer hidden at construction never paints"
    finally:
        window.close()


def test_primer_self_destructs_on_first_frame(qapp):
    """One-shot primer: first successful RHI init removes it (no lingering child)."""
    import shiboken6

    window = QWidget()
    try:
        ensure_window_rhi(window)
        primer = window.findChild(QRhiWidget, "rhi_surface_primer")
        assert primer is not None
        primer.initialize(None)  # first successful RHI setup (render thread, live)
        QApplication.sendPostedEvents(primer, QEvent.Type.DeferredDelete)
        assert window.findChild(QRhiWidget, "rhi_surface_primer") is None
        assert not shiboken6.isValid(primer)
    finally:
        window.close()


def test_primer_failure_does_not_persist_backend_fallback(qapp, monkeypatch):
    """A throwaway primer must never flip the stored backend setting.

    The real-canvas ``renderFailed`` handler persists the platform fallback
    on failure; the primer fails on every offscreen/software run by
    construction, so wiring that handler to it would rewrite the user's
    stored backend before any real canvas exists.
    """
    import ui.canvas_infra.rhi.rhi_backend as mod

    calls: list = []
    monkeypatch.setattr(
        mod, "persist_rhi_backend_setting", lambda name: calls.append(name)
    )
    window = QWidget()
    try:
        ensure_window_rhi(window)
        primer = window.findChild(QRhiWidget, "rhi_surface_primer")
        assert primer is not None
        primer.renderFailed.emit()
        _drain()
        assert calls == []
    finally:
        window.close()
