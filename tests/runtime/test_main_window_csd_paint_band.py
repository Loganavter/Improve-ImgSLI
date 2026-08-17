"""CSD resize band must collapse in maximized/fullscreen.

Regression: the frameless surface carries a transparent outer band (for
edge-resize grabs). The window paintEvent insets the rounded body and the
root layout insets all content by that band — in maximized/fullscreen the
window cannot be edge-resized, but the insets were kept, leaving an
invisible strip around the window that window-capture tools include
(transparent before, painted with the window background after the body
started filling the whole surface).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QVBoxLayout, QWidget

from shared_toolkit.ui.decorate_dialog import resolve_csd_band
from ui.main_window.window import MainWindow


def _make_window(qapp) -> QWidget:
    window = QWidget()
    window.setProperty("_csd_outer_band", 8)
    return window


def test_csd_band_applies_in_windowed_mode(qapp):
    window = _make_window(qapp)
    assert resolve_csd_band(window) == 8
    window.deleteLater()
    qapp.processEvents()


def test_csd_band_zeroed_when_maximized(qapp, monkeypatch):
    window = _make_window(qapp)
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    assert resolve_csd_band(window) == 0


def test_csd_band_zeroed_when_fullscreen(qapp, monkeypatch):
    window = _make_window(qapp)
    monkeypatch.setattr(window, "isFullScreen", lambda: True)
    assert resolve_csd_band(window) == 0


def _margins(layout) -> tuple:
    m = layout.contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def test_content_inset_sync_collapses_band_when_maximized(qapp, monkeypatch):
    window = _make_window(qapp)
    window._root_layout = QVBoxLayout(window)
    window.startup_runtime = None
    monkeypatch.setattr(window, "isFullScreen", lambda: True)
    MainWindow._sync_csd_content_band(window)
    assert _margins(window._root_layout) == (0, 0, 0, 0)


def test_content_inset_sync_restores_band_in_windowed_mode(qapp):
    window = _make_window(qapp)
    window._root_layout = QVBoxLayout(window)
    window.startup_runtime = None
    MainWindow._sync_csd_content_band(window)
    assert _margins(window._root_layout) == (8, 8, 8, 8)
