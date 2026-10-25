"""Wave A seam: content-scoped overlay layer below the AdaptiveTabStrip.

Frozen seam contract (plan-2026-09-25-content-below-strip, section 11):
tab-owned overlays parent/clamp to the content layer/bounds
(host = ``workspace_content_widget``); global menus/dialogs/CSD/help stay
on the window layer, untouched.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.overlay_layer import (
    OverlayLayer,
    content_bounds,
    get_content_overlay_layer,
    get_overlay_layer,
)
from core.log_names import APP_LOGGER_NAME

WINDOW_W, WINDOW_H = 800, 600
STRIP_H = 100  # tab-strip band on top; content lives strictly below it.


def _make_shell():
    """Window with a strip band on top + content host below (no .show needed)."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    strip = QWidget(window)
    strip.setObjectName("WorkspaceTabsBar")
    strip.setGeometry(0, 0, WINDOW_W, STRIP_H)
    content = QWidget(window)
    content.setGeometry(0, STRIP_H, WINDOW_W, WINDOW_H - STRIP_H)
    window.workspace_content_widget = content
    tab_page = QWidget(content)
    tab_page.setGeometry(0, 0, WINDOW_W, WINDOW_H - STRIP_H)
    return window, content, tab_page


def test_content_layer_host_is_workspace_content_widget(qapp):
    window, content, tab_page = _make_shell()
    try:
        layer = get_content_overlay_layer(tab_page)
        assert layer is not None
        assert layer.host is content
        # Resolving from the content host itself or the window agrees.
        assert get_content_overlay_layer(content).host is content
        assert get_content_overlay_layer(window).host is content
        # Cached: same instance, still content-hosted.
        assert get_content_overlay_layer(tab_page) is layer
    finally:
        window.deleteLater()


def test_content_bounds_is_host_rect(qapp):
    window, content, tab_page = _make_shell()
    try:
        bounds = content_bounds(tab_page)
        assert bounds == QRect(0, 0, WINDOW_W, WINDOW_H - STRIP_H)
    finally:
        window.deleteLater()


def test_clamp_rect_keeps_popup_inside_content_bounds(qapp):
    """A popup reaching into the strip band is pulled back into content."""
    window, content, tab_page = _make_shell()
    try:
        layer = get_content_overlay_layer(tab_page)
        assert layer is not None
        margin = 8
        # Content-local y < 0 == the strip band in window coords: must clamp.
        above = layer.clamp_rect(QRect(50, -200, 120, 80), margin=margin)
        assert above.y() >= margin
        assert above.x() >= margin
        inner = content.rect().adjusted(margin, margin, -margin, -margin)
        assert inner.contains(above)
        # A popup already inside content is not pushed into the strip.
        inside = layer.clamp_rect(QRect(50, 50, 120, 80), margin=margin)
        assert inside == QRect(50, 50, 120, 80)
        assert inside.y() >= 0
    finally:
        window.deleteLater()


def test_fallback_returns_window_layer_when_content_host_absent(qapp, caplog):
    """Startup window without a content host: window layer + warning."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    child = QWidget(window)
    try:
        with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
            layer = get_content_overlay_layer(child)
        assert layer is window.overlay_layer
        assert any(
            "workspace_content_widget" in rec.getMessage()
            for rec in caplog.records
        )
    finally:
        window.deleteLater()


def test_window_layer_clamp_unchanged(qapp):
    """Global path (window host) still clamps to window bounds, not content."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    try:
        layer = get_overlay_layer(window)
        assert layer is not None
        assert getattr(layer, "_is_content_layer", False) is False
        # Top-left of the *window* (strip band) is a legal spot for globals.
        assert layer.clamp_rect(QRect(8, 8, 120, 80)) == QRect(8, 8, 120, 80)
        # Oversized popup shrinks to window bounds, as before.
        shrunk = layer.clamp_rect(QRect(-50, -50, 4000, 4000))
        assert shrunk.size() == window.rect().adjusted(8, 8, -8, -8).size()
    finally:
        window.deleteLater()
