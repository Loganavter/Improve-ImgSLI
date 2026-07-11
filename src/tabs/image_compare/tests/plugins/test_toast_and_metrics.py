"""Toast + metrics: split-rounding progress toast, SSIM toast only outside
diff-mode (deduplicated), and export save-flow progress updates.

Dogma source: docs/dev/ARCHITECTURE.md (toast/metrics notifications via events).
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_compare.services.analysis.metrics import MetricsService
from tabs.image_compare.services.analysis.runtime import (
    AnalysisRuntime,
    CoreUpdateDispatcher,
    UIUpdateDispatcher,
)
from tabs.image_compare.services.export_save_flow import ExportSaveFlowCoordinator
from sli_ui_toolkit.ui.widgets.composite.toast import ToastNotification

APP = QApplication.instance() or QApplication([])

class _FakeToastManager:
    def __init__(self):
        self.shown = []
        self.updated = []
        self.closed = []

    def show_toast(self, message, **kwargs):
        self.shown.append((message, kwargs))
        return 77

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)

def _build_metrics_service(diff_mode: str = "off"):
    toast_manager = _FakeToastManager()
    runtime = AnalysisRuntime(
        thread_pool=None,
        ui_updates=UIUpdateDispatcher(),
        core_updates=CoreUpdateDispatcher(),
        toast_manager_getter=lambda: toast_manager,
    )
    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode=diff_mode),
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(
                    auto_calculate_psnr=False,
                    auto_calculate_ssim=False,
                    psnr_value=None,
                    ssim_value=None,
                )
            ),
        ),
    )
    return MetricsService(store, runtime), toast_manager

def test_toast_notification_marks_progress_state_for_split_rounding():
    host = QWidget()
    toast = ToastNotification(host)

    toast.show_message("Saving", max_width=280, progress=None)
    assert toast.content_widget.property("hasProgress") is False
    assert toast.progress_container.property("hasProgress") is False

    toast.show_message("Saving", max_width=280, progress=25)
    assert toast.content_widget.property("hasProgress") is True
    assert toast.progress_container.property("hasProgress") is True

def test_metrics_service_shows_ssim_toast_outside_diff_mode():
    service, toast_manager = _build_metrics_service(diff_mode="off")

    service._show_ssim_metrics_toast_if_needed(True)
    service._complete_ssim_metrics_toast(success=True)

    assert len(toast_manager.shown) == 1
    assert toast_manager.shown[0][1]["progress"] == 0
    assert toast_manager.updated[0][2]["progress"] == 100
    assert toast_manager.updated[0][2]["success"] is True

def test_metrics_service_skips_duplicate_ssim_toast_for_diff_mode():
    service, toast_manager = _build_metrics_service(diff_mode="ssim")

    service._show_ssim_metrics_toast_if_needed(True)

    assert toast_manager.shown == []

def test_export_save_flow_updates_toast_progress():
    toast_manager = _FakeToastManager()
    coordinator = ExportSaveFlowCoordinator(
        store=None,
        main_window_app=SimpleNamespace(toast_manager=toast_manager),
        ui_manager=None,
        tr_func=lambda key: {
            "msg.saving": "Saving",
        }.get(key, key),
        state_coordinator=None,
        export_service=SimpleNamespace(export_image=lambda **_kwargs: None),
    )
    coordinator._save_cancellation[5] = object()

    coordinator._on_save_worker_progress(5, "/tmp/result.png", 30)

    assert toast_manager.updated[0][0] == 5
    assert toast_manager.updated[0][2]["progress"] == 30
    assert toast_manager.updated[0][2]["success"] is False
