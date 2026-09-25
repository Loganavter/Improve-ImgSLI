"""Wave D (phase 2): anchored flyouts clamp to the content below AdaptiveTabStrip.

CLAMP ONLY, NO REPARENT. Global menus/dialogs/CSD untouched.

- Content-anchored popups (``AnchoredPopupBubbleController.show`` with the
  anchor in the below-strip subtree) never overlap the tab-strip band.
- Global-chrome anchors (startup, menus, CSD) keep byte-identical geometry.
- ``WorkspaceTabCarryHint`` paints ON the strip tabs BY DESIGN (the
  intentional exception); its overlay geometry is narrowed to the tabs rect
  with identical tab-target mapping.
- Startup / non-widget doubles fail open, never crash.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.overlay_layer import (
    OverlayLayer,
    get_content_overlay_layer,
    get_overlay_layer,
)
from ui.managers.transient_ui_parts.anchored_popup import (
    AnchoredPopupBubbleController,
)
from ui.main_window.workspace_tab_carry_hint import _TabCarryHintOverlay

WINDOW_W, WINDOW_H = 800, 600
STRIP_H = 100  # tab-strip band on top; content lives strictly below it.


def _make_shell():
    """Window with strip band + content host; anchor hugging the content top."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    strip = QWidget(window)
    strip.setGeometry(0, 0, WINDOW_W, STRIP_H)
    content = QWidget(window)
    content.setGeometry(0, STRIP_H, WINDOW_W, WINDOW_H - STRIP_H)
    window.workspace_content_widget = content
    window.ui = SimpleNamespace(workspace_tabs=strip)
    anchor = QWidget(content)
    anchor.setGeometry(50, 0, 100, 20)  # top edge of content: "top" popup leaks up
    return window, strip, content, anchor


def _strip_global(strip: QWidget) -> QRect:
    return QRect(strip.mapToGlobal(QPoint(0, 0)), strip.size())


def test_content_anchored_popup_disjoint_from_strip(qapp):
    """A content-anchored popup never overlaps the strip band."""
    window, strip, _content, anchor = _make_shell()
    try:
        layer = get_content_overlay_layer(anchor)
        assert layer is not None and getattr(layer, "_is_content_layer", False)
        controller = AnchoredPopupBubbleController(
            host=window, popup_key="wave-d-content", auto_hide_delay_ms=60000
        )
        try:
            assert controller.show(
                anchor_widget=anchor,
                text="3",
                size=QSize(120, 60),
                position="top",
            )
            popup = get_overlay_layer(anchor)._value_popups["wave-d-content"]
            geom = popup.geometry()
            assert geom.isValid()
            assert not geom.intersects(_strip_global(strip)), (
                f"content popup {geom} overlaps the strip {_strip_global(strip)}"
            )
        finally:
            controller.hide()
    finally:
        window.deleteLater()


def test_global_anchored_popup_geometry_unchanged(qapp):
    """Window-chrome anchors keep byte-identical legacy placement."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    anchor = QWidget(window)
    anchor.setGeometry(300, 300, 100, 20)
    try:
        # No content host: startup-like fallback to the window layer.
        assert getattr(get_content_overlay_layer(anchor), "_is_content_layer", False) is False
        controller = AnchoredPopupBubbleController(
            host=window, popup_key="wave-d-global", auto_hide_delay_ms=60000
        )
        try:
            assert controller.show(
                anchor_widget=anchor,
                text="3",
                size=QSize(120, 60),
                position="top",
            )
            layer = get_overlay_layer(anchor)
            popup = layer._value_popups["wave-d-global"]
            legacy = layer.place_global_rect_relative_to_anchor(
                anchor, popup.size(), position="top", offset=6
            )
            assert popup.geometry() == legacy
        finally:
            controller.hide()
    finally:
        window.deleteLater()


def test_carry_overlay_geometry_is_tabs_rect(qapp):
    """Overlay shrinks to the tabs rect; tab targets map identically."""
    host = QWidget()
    host.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    tabs = QWidget(host)
    tabs.setGeometry(0, 0, WINDOW_W, STRIP_H)
    host.ui = SimpleNamespace(workspace_tabs=tabs)
    overlay = _TabCarryHintOverlay(host)
    try:
        targets = [(QRect(10, 10, 80, 80), False), (QRect(100, 10, 80, 80), True)]
        overlay.set_targets(targets, phase=0.0)
        expected = QRect(tabs.mapTo(host, QPoint(0, 0)), tabs.size())
        assert overlay.geometry() == expected
        assert overlay.geometry() != host.rect()
        # Identical tab-target mapping: overlay-local + origin == parent coords.
        origin = overlay.geometry().topLeft()
        for (original, _hovered), (stored, _s_hovered) in zip(targets, overlay._rects):
            assert QRect(stored.topLeft() + origin, stored.size()) == original
    finally:
        overlay.deleteLater()
        host.deleteLater()


def test_startup_and_non_widget_doubles_do_not_crash(qapp):
    """Fail-open everywhere: no host, no content, non-widget anchors."""
    window = QWidget()
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    window.overlay_layer = OverlayLayer(window)
    try:
        controller = AnchoredPopupBubbleController(
            host=window, popup_key="wave-d-doubles", auto_hide_delay_ms=60000
        )
        try:
            # Non-widget double: no overlay resolves → False, no exception.
            double = SimpleNamespace(
                parentWidget=lambda: None,
                window=lambda: None,
            )
            assert controller.show(anchor_widget=double, size=QSize(60, 30)) is False
            # None anchor likewise fails open.
            assert controller.show(anchor_widget=None, size=QSize(60, 30)) is False
        finally:
            controller.hide()
        # Carry overlay without any tabs attrs falls back to the host rect.
        bare_host = QWidget()
        bare_host.setGeometry(0, 0, WINDOW_W, WINDOW_H)
        overlay = _TabCarryHintOverlay(bare_host)
        try:
            overlay.set_targets([(QRect(5, 5, 40, 40), False)], phase=0.0)
            assert overlay.geometry() == bare_host.rect()
        finally:
            overlay.deleteLater()
            bare_host.deleteLater()
    finally:
        window.deleteLater()
