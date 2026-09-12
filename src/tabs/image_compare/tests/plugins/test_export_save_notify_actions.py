"""Save-success notify must reach MainWindowActions, not QWidget.actions().

Regression: `main_window_app` is the MainWindow *widget*, so
`main_window_app.actions` is the Qt builtin `QWidget.actions()` (a
`builtin_function_or_method`) — `save_flow._on_success_notify` crashed with
`AttributeError: ... has no attribute 'set_last_saved_path'`, silently
dropping tray-visibility + system-notification bookkeeping. The manager lives
at `.action_registry` (ui/main_window/window.py).
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_compare.services.image_export.save_flow import (
    ExportSaveFlowCoordinator,
)


def _flow(app):
    store = SimpleNamespace(
        settings=SimpleNamespace(system_notifications_enabled=False)
    )
    return ExportSaveFlowCoordinator(
        store=store,
        main_window_app=app,
        ui_manager=SimpleNamespace(),
        tr_func=lambda key: key,
        state_coordinator=SimpleNamespace(),
        export_service=SimpleNamespace(),
    )


class _Recorder:
    def __init__(self):
        self.last_saved = None
        self.tray_updated = False

    def set_last_saved_path(self, path):
        self.last_saved = path

    def update_tray_actions_visibility(self):
        self.tray_updated = True


def test_notify_uses_action_registry(caplog):
    rec = _Recorder()
    app = SimpleNamespace(
        action_registry=rec, thread_pool=None, toast_manager=None
    )
    flow = _flow(app)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        flow._on_success_notify("/tmp/shot.png")
    assert rec.last_saved == "/tmp/shot.png"
    assert rec.tray_updated is True
    assert "Save notification failed" not in caplog.text


def test_widget_actions_builtin_is_skipped_gracefully(caplog):
    """Exact user repro: `.actions` is a builtin method (QWidget.actions)."""
    app = SimpleNamespace(
        actions=[].append,  # builtin_function_or_method, like QWidget.actions
        thread_pool=None,
        toast_manager=None,
    )
    flow = _flow(app)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        flow._on_success_notify("/tmp/shot.png")  # must not raise
    assert "no action manager" in caplog.text
    assert "Save notification failed" not in caplog.text
