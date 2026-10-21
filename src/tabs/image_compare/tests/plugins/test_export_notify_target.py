"""Target bug: the export "saved" notification calls ``window.actions``, which
on the real ``MainWindow`` is ``QWidget.actions()`` — a builtin method.

Bug row: "IC/video export success notification silently never fires"
(``docs/bugs/README.md``; live log 2026-10-21 13:55:12).

Observed at the branch base (``11a1c768``): ``ExportSaveFlowCoordinator``
(``src/tabs/image_compare/services/image_export/save_flow.py:48``) and
``VideoExportFlow._notify_export_success``
(``src/tabs/image_compare/plugins/video_editor/services/export_flow.py:307``)
read ``self.main_window_app.actions``. ``MainWindow`` stores the action owner as
``action_registry`` (``src/ui/main_window/window.py:88``) and never sets
``actions``, so the attribute lookup falls through to ``QWidget.actions()`` and
the call raises ``AttributeError: 'builtin_function_or_method' object has no
attribute 'set_last_saved_path'``. Both call sites swallow the exception, so the
tray "open last saved" state and the system notification are silently skipped —
a green suite proved nothing because the fakes carry no ``actions``/``QWidget``
trap at all.

The probe drives both real call sites with a real ``QWidget`` window whose action
owner sits on ``action_registry`` (the shipped attribute) and asserts the
observable outcome: the path is recorded, the tray refresh runs, the system
notification is sent.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_compare.plugins.video_editor.services.export_flow import (
    VideoExportFlow,
)
from tabs.image_compare.services.image_export.save_flow import (
    ExportSaveFlowCoordinator,
)

BUG_ID = "bug.export_notify_actions"


class _Recorder:
    """Stands in for ``MainWindowActions``; records what the notify path did."""

    def __init__(self) -> None:
        self.saved_paths: list[str | None] = []
        self.tray_updates = 0
        self.notifications: list[tuple[str, str, str | None]] = []

    def set_last_saved_path(self, path: str | None) -> None:
        self.saved_paths.append(path)

    def update_tray_actions_visibility(self) -> None:
        self.tray_updates += 1

    def notify_system(
        self,
        title: str,
        message: str,
        image_path: str | None = None,
        timeout_ms: int = 4000,
    ) -> None:
        self.notifications.append((title, message, image_path))


class _WidgetWindow(QWidget):
    """A real ``QWidget``: ``.actions`` resolves to ``QWidget.actions()``.

    That is exactly the trap the shipped ``MainWindow`` exposes — it carries the
    action owner on ``action_registry`` (``ui/main_window/window.py:88``).
    """

    def __init__(self) -> None:
        super().__init__()
        self.action_registry = _Recorder()
        self.tray_manager = None
        self.toast_manager = None
        self.thread_pool = None


def _window() -> _WidgetWindow:
    QApplication.instance() or QApplication([])
    return _WidgetWindow()


@pytest.fixture(autouse=True)
def _fresh_journal():
    reset_journal()
    yield
    reset_journal()


def _ic_coordinator(window: _WidgetWindow) -> ExportSaveFlowCoordinator:
    return ExportSaveFlowCoordinator(
        store=SimpleNamespace(
            settings=SimpleNamespace(system_notifications_enabled=True),
        ),
        main_window_app=window,
        ui_manager=None,
        tr_func=lambda key: key,
        state_coordinator=None,
        export_service=SimpleNamespace(export_image=lambda **_kwargs: None),
    )


def _video_flow(window: _WidgetWindow) -> VideoExportFlow:
    controller = SimpleNamespace(
        main_controller=SimpleNamespace(
            store=SimpleNamespace(
                settings=SimpleNamespace(current_language="en"),
            ),
        ),
        presenter=SimpleNamespace(main_window_app=window),
    )
    return VideoExportFlow(controller)


def test_export_notify_repro_and_fix(tmp_path: Path, caplog) -> None:
    png = tmp_path / "result.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    video = tmp_path / "export.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    window = _window()
    recorder: _Recorder = window.action_registry

    with caplog.at_level(logging.ERROR, logger="ImproveImgSLI"):
        _ic_coordinator(window)._on_success_notify(str(png))
        _video_flow(window)._notify_export_success(str(video), None)

    saved = list(recorder.saved_paths)
    notifications = len(recorder.notifications)
    tray_updates = recorder.tray_updates
    swallowed = [
        line.split(":", 1)[-1].strip()
        for line in caplog.text.splitlines()
        if "Set the environment variable QT_QPA_PLATFORM" not in line
        and ("Save notification failed" in line or "video export success" in line)
    ]
    signal = (
        f"window.actions={type(window.actions).__name__} "
        f"saved_paths={saved} tray_updates={tray_updates} "
        f"notifications={notifications} swallowed={swallowed}"
    )
    ids = (
        "tabs/image_compare/services/image_export/save_flow.py::_on_success_notify",
        "tabs/image_compare/plugins/video_editor/services/export_flow.py::_notify_export_success",
        "ui/main_window/window.py::MainWindow.action_registry",
    )

    bug_present = (
        saved != [str(png)]
        or tray_updates != 1
        or notifications != 2
    )
    if bug_present:
        record_evidence(
            BUG_ID,
            kind="target_bug",
            verdict="reproduced",
            signal=signal,
            reason=(
                "the notify path read window.actions (QWidget.actions() builtin), "
                "raised AttributeError and the swallowed exception left the tray "
                "and system notification untouched"
            ),
            ids=ids,
            area="tabs.image_compare.services.image_export",
        )
        pytest.fail(f"reproduced: {signal}")

    record_evidence(
        BUG_ID,
        kind="target_bug",
        verdict="fixed",
        signal=signal,
        reason=(
            "both export notify sites resolved the action owner through "
            "action_registry: path recorded, tray refreshed, two notifications sent"
        ),
        ids=ids,
        area="tabs.image_compare.services.image_export",
    )
    assert verdict(None, BUG_ID).verdict == "fixed"
    assert recorder.notifications[0][2] == str(png)  # icon only for a real file
    assert recorder.notifications[1][2] is None
