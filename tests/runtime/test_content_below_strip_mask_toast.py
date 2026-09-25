"""Wave C: transition cover + toast anchor pinned below the tab strip.

Plan plan-2026-09-25-content-below-strip, phase 3: ``mask.cover()`` only
ever targets ``workspace_stack`` (or its children) inside
``workspace_content_widget`` — a window-level target is refused with a
cover-skipped warning; toast anchors come only from the active tab's
``create_service("toast_anchor_widget")`` canvas and are accepted only
inside the below-strip content subtree, so toasts can never cover the
strip. Layout invariant: ``strip.bottom <= stack.top``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from shared_toolkit.ui.overlay_layer import (
    content_bounds,
    get_content_overlay_layer,
)
from ui.main_window.ui import Ui_ImageComparisonApp, _widget_in_content_subtree
from ui.main_window.workspace_transition_mask import WorkspaceTransitionMask
from ui.presenters.main_window.workspace import (
    _cover_target_below_strip,
    _cover_transition_for_session,
)

WINDOW_W, WINDOW_H = 800, 600
STRIP_H = 60


def _make_shell():
    """Window with strip on top + workspace content (stack + page) below."""
    window = QWidget()
    window.setObjectName("MainWindow")
    window.setGeometry(0, 0, WINDOW_W, WINDOW_H)
    strip = QWidget(window)
    strip.setObjectName("WorkspaceTabsBar")
    strip.setGeometry(0, 0, WINDOW_W, STRIP_H)
    content = QWidget(window)
    content.setObjectName("workspace_content_widget")
    content.setGeometry(0, STRIP_H, WINDOW_W, WINDOW_H - STRIP_H)
    # Same exposure as LayoutComposer: attribute on the window.
    window.workspace_content_widget = content
    stack = QStackedWidget(content)
    stack.setObjectName("workspace_stack")
    stack.setGeometry(0, 0, WINDOW_W, WINDOW_H - STRIP_H)
    page = QWidget()
    stack.addWidget(page)
    stack.setCurrentWidget(page)
    anchor = QLabel("canvas", parent=page)
    anchor.setObjectName("CanvasAnchor")
    anchor.setGeometry(10, 10, 200, 100)
    return SimpleNamespace(
        window=window,
        strip=strip,
        content=content,
        stack=stack,
        page=page,
        anchor=anchor,
    )


def _presenter_for_cover(shell, mask, *, stack_override=None):
    session = SimpleNamespace(id="s1", session_type="image_compare")
    hint = SimpleNamespace(
        cover_on_enter=True, min_duration_ms=0, max_duration_ms=60000
    )
    tab = SimpleNamespace(transition_hint=lambda: hint)
    manager = SimpleNamespace(
        get_active_session=lambda: session,
        list_sessions=lambda: (session,),
    )
    shell.window._workspace_transition_mask = mask
    ui = SimpleNamespace(
        main_window=shell.window,
        workspace_stack=(
            stack_override if stack_override is not None else shell.stack
        ),
        workspace_content_widget=shell.content,
        _tab_registry=SimpleNamespace(get_tab=lambda _t: tab),
    )
    return SimpleNamespace(
        _last_covered_session_id=None,
        session_manager=manager,
        ui=ui,
        main_window_app=shell.window,
    )


def test_strip_bottom_above_stack_top(qapp):
    shell = _make_shell()
    try:
        window = shell.window
        strip_bottom = shell.strip.mapTo(window, shell.strip.rect().bottomLeft()).y()
        stack_top = shell.stack.mapTo(window, QPoint(0, 0)).y()
        assert strip_bottom <= stack_top
    finally:
        shell.window.deleteLater()


def test_cover_stack_shows_overlay_inside_content(qapp):
    shell = _make_shell()
    try:
        # Frozen seam agrees: content bounds are the host rect (no strip).
        bounds = content_bounds(shell.stack)
        assert bounds == shell.content.rect()
        layer = get_content_overlay_layer(shell.stack)
        assert layer is not None
        assert layer.host is shell.content

        mask = WorkspaceTransitionMask(shell.window)
        # Visibility needs a shown top-level (offscreen platform is fine).
        shell.window.show()
        mask.cover(
            shell.stack,
            min_duration_ms=0,
            max_duration_ms=60000,
            session_type="image_compare",
        )
        overlay = mask._overlay
        assert overlay is not None
        assert overlay.isVisible()
        # Overlay is parented to the window; its rect must sit inside the
        # content rect mapped to the same coordinates.
        content_origin = shell.content.mapTo(shell.window, QPoint(0, 0))
        content_rect = QRect(content_origin, shell.content.size())
        assert content_rect.contains(overlay.geometry())
        # ... and strictly below the strip band.
        strip_bottom = shell.strip.mapTo(
            shell.window, shell.strip.rect().bottomLeft()
        ).y()
        assert overlay.geometry().top() >= strip_bottom
        mask._overlay.hide()
    finally:
        shell.window.deleteLater()


def test_cover_window_target_refused(qapp):
    shell = _make_shell()
    try:
        # Guard level: the window itself is not below the strip.
        assert _cover_target_below_strip(shell.stack, shell.content) is True
        assert (
            _cover_target_below_strip(shell.stack.currentWidget(), shell.content)
            is True
        )
        assert _cover_target_below_strip(shell.window, shell.content) is False
        assert _cover_target_below_strip(None, shell.content) is True  # mask warns
        assert _cover_target_below_strip(object(), shell.content) is True  # fail-open

        # Caller level: stack target covers ...
        mask = MagicMock()
        presenter = _presenter_for_cover(shell, mask)
        _cover_transition_for_session(presenter, "s1")
        mask.cover.assert_called_once()
        assert mask.cover.call_args.args[0] is shell.stack

        # ... while a window-level target is skipped (cover-skipped style).
        mask2 = MagicMock()
        presenter2 = _presenter_for_cover(
            shell, mask2, stack_override=shell.window
        )
        _cover_transition_for_session(presenter2, "s1")
        mask2.cover.assert_not_called()
    finally:
        shell.window.deleteLater()


def _sync_ui(shell, anchor_widget):
    """Drive Ui_ImageComparisonApp.sync_session_mode with fakes."""
    ui = Ui_ImageComparisonApp.__new__(Ui_ImageComparisonApp)
    toast_manager = MagicMock()
    shell.window.toast_manager = toast_manager
    page = shell.stack.currentWidget()
    ui.workspace_stack = shell.stack
    ui.workspace_content_widget = shell.content
    ui._tab_registry = SimpleNamespace(
        activate=lambda _t: None,
        get_page=lambda _t: page,
        create_service=lambda _sid: anchor_widget,
        apply_host_session_mode=lambda *a, **k: True,
        flush_stale_appearance=lambda _w: None,
    )
    ui.sync_session_mode("image_compare", "title")
    return toast_manager


def test_toast_anchor_accepted_inside_content(qapp):
    shell = _make_shell()
    try:
        assert _widget_in_content_subtree(shell.anchor, shell.content) is True
        toast_manager = _sync_ui(shell, shell.anchor)
        toast_manager.set_anchor.assert_called_once_with(shell.anchor)
    finally:
        shell.window.deleteLater()


def test_toast_anchor_refused_outside_content(qapp):
    shell = _make_shell()
    try:
        stray = QLabel("window-level", parent=shell.window)
        stray.setGeometry(0, 0, 100, 20)
        assert _widget_in_content_subtree(stray, shell.content) is False
        assert _widget_in_content_subtree(shell.window, shell.content) is False
        toast_manager = _sync_ui(shell, stray)
        toast_manager.set_anchor.assert_not_called()
    finally:
        shell.window.deleteLater()
