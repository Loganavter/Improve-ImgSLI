"""Phase A close-leaks: IC decode/metrics/diff sticky-toast terminals."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown = []
        self.updated = []
        self.closed = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _FakeToastCoordinator:
    def __init__(self, manager):
        self._manager = manager
        self._loading_toasts = {}

    def show(self, slot_id):
        self._loading_toasts[slot_id] = self._manager.show_toast("loading", duration=0)

    def dismiss(self, slot_id):
        toast_id = self._loading_toasts.pop(slot_id, None)
        if toast_id is not None:
            self._manager.close_toast(toast_id)

    def finish(self, slot_id):
        toast_id = self._loading_toasts.pop(slot_id, None)
        if toast_id is not None:
            self._manager.update_toast(toast_id, "done", success=True, duration=2000, progress=100)


def _make_ic_controller(manager):
    coord = _FakeToastCoordinator(manager)
    bus_emitted = []
    err_emitted = []
    return SimpleNamespace(
        _loading_toast_coordinator=coord,
        _loading_toasts=coord._loading_toasts,
        _get_crop_service=lambda: None,
        _get_toast_manager=lambda: manager,
        event_bus=SimpleNamespace(emitted=bus_emitted, emit=bus_emitted.append),
        store=SimpleNamespace(
            settings=SimpleNamespace(current_language="en"),
            get_session_state_slot=lambda _name: SimpleNamespace(
                image1_path="/tmp/a.png", image2_path="/tmp/b.png"
            ),
        ),
        error_occurred=SimpleNamespace(emitted=err_emitted, emit=err_emitted.append),
        presenter=SimpleNamespace(main_window_app=SimpleNamespace(toast_manager=manager)),
    )


def test_ic_preview_decode_error_dismisses_toast_and_emits_dialog():
    from tabs.image_compare.use_cases import image_decode as ic_decode

    manager = _FakeToastManager()
    controller = _make_ic_controller(manager)
    controller.event_bus = None  # force error_occurred path
    controller._loading_toast_coordinator.show(1)

    result = ic_decode.load_image_async(controller, "/tmp/a.png", 1, 0)

    assert result[0] is None
    assert manager.closed, "decode failure must dismiss the loading toast"
    assert controller.error_occurred.emitted, "decode failure must still emit dialog event"


def test_ic_full_res_error_dismisses_toast_and_emits_dialog():
    from tabs.image_compare.use_cases import image_decode as ic_decode

    manager = _FakeToastManager()
    controller = _make_ic_controller(manager)
    controller.event_bus = None
    controller._loading_toast_coordinator.show(1)

    ic_decode.on_full_resolution_error(controller, "/tmp/a.png", RuntimeError("bad pixels"))

    assert manager.closed, "full-res failure must dismiss the loading toast"
    assert controller.error_occurred.emitted


def _make_metrics_service(manager, *, diff_mode="off", thread_pool=None):
    from tabs.image_compare.services.analysis.metrics import MetricsService
    from tabs.image_compare.services.analysis.runtime import (
        AnalysisRuntime,
        CoreUpdateDispatcher,
        UIUpdateDispatcher,
    )

    runtime = AnalysisRuntime(
        thread_pool=thread_pool,
        ui_updates=UIUpdateDispatcher(),
        core_updates=CoreUpdateDispatcher(),
        toast_manager_getter=lambda: manager,
    )
    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(diff_mode=diff_mode),
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(
                    auto_calculate_psnr=False,
                    auto_calculate_ssim=True,
                    psnr_value=None,
                    ssim_value=None,
                    image1=SimpleNamespace(size=(8, 8)),
                    image2=SimpleNamespace(size=(8, 8)),
                )
            ),
        ),
    )
    return MetricsService(store, runtime)


def test_metrics_no_pool_closes_orphaned_toast():
    manager = _FakeToastManager()
    service = _make_metrics_service(manager, thread_pool=None)
    service._active_ssim_toast_id = manager.show_toast("SSIM...", duration=0)
    service._ssim_toast_request_id = service._metrics_request_id

    service.calculate_metrics_async(calc_psnr=False, calc_ssim=True)

    assert service._active_ssim_toast_id is None
    assert manager.closed, "no-pool exit must close the orphaned toast"


def test_metrics_stale_result_keeps_newer_owners_toast():
    manager = _FakeToastManager()
    service = _make_metrics_service(manager, thread_pool=None)
    first = manager.show_toast("SSIM...", duration=0)
    service._active_ssim_toast_id = first
    service._metrics_request_id = 5
    service._ssim_toast_request_id = 5
    # Newer request reuses the same toast id.
    service._metrics_request_id = 6
    service._ssim_toast_request_id = 6

    service.on_metrics_calculated((10.0, 0.9), request_id=5)

    assert service._active_ssim_toast_id == first
    assert manager.closed == []


def test_metrics_stale_result_closes_abandoned_toast():
    manager = _FakeToastManager()
    service = _make_metrics_service(manager, thread_pool=None)
    first = manager.show_toast("SSIM...", duration=0)
    service._active_ssim_toast_id = first
    service._metrics_request_id = 6
    service._ssim_toast_request_id = 5  # toast still owned by stale request

    service.on_metrics_calculated((10.0, 0.9), request_id=5)

    assert service._active_ssim_toast_id is None
    assert manager.closed == [first]


def test_metrics_mode_flip_closes_toast():
    manager = _FakeToastManager()
    service = _make_metrics_service(manager, diff_mode="ssim")
    service._active_ssim_toast_id = manager.show_toast("SSIM...", duration=0)

    service._show_ssim_metrics_toast_if_needed(True)

    assert service._active_ssim_toast_id is None
    assert manager.closed


def _make_presenter(manager, toast_id=None, key=None):
    return SimpleNamespace(
        main_window_app=SimpleNamespace(toast_manager=manager),
        _active_diff_toast_id=toast_id,
        _active_diff_toast_key=key,
        store=SimpleNamespace(
            settings=SimpleNamespace(current_language="en"),
            viewport=SimpleNamespace(view_state=SimpleNamespace(diff_mode="ssim")),
        ),
    )


def test_diff_key_mismatch_closes_stale_toast():
    from tabs.image_compare.presenters.image_canvas.background_parts import diff_toasts

    manager = _FakeToastManager()
    tid = manager.show_toast("SSIM...", duration=0)
    presenter = _make_presenter(manager, toast_id=tid, key="key-A")

    diff_toasts.complete_diff_toast(presenter, "key-B")

    assert manager.closed == [tid]
    assert presenter._active_diff_toast_id is None
    assert presenter._active_diff_toast_key is None


def test_diff_complete_without_manager_keeps_id():
    from tabs.image_compare.presenters.image_canvas.background_parts import diff_toasts

    presenter = _make_presenter(None, toast_id=42, key="key-A")

    diff_toasts.complete_diff_toast(presenter, "key-A")

    assert presenter._active_diff_toast_id == 42
    assert presenter._active_diff_toast_key == "key-A"


def test_lifecycle_invalidate_without_manager_keeps_id():
    from tabs.image_compare.presenters.image_canvas import lifecycle as ic_lifecycle

    presenter = _make_presenter(
        None, toast_id=42, key="key-A",
    )
    presenter._last_bg_signature = object()
    presenter._last_mag_signature = object()
    presenter._last_img_sig = object()
    presenter._cached_base_pixmap = object()
    presenter.current_displayed_pixmap = object()
    presenter._pending_interactive_mode = None
    presenter._pending_cached_diff_request_key = "k"

    ic_lifecycle.invalidate_render_state(presenter)

    assert presenter._active_diff_toast_id == 42


def test_lifecycle_invalidate_with_manager_closes_and_clears():
    from tabs.image_compare.presenters.image_canvas import lifecycle as ic_lifecycle

    manager = _FakeToastManager()
    presenter = _make_presenter(manager, toast_id=77, key="key-A")
    presenter._last_bg_signature = object()
    presenter._last_mag_signature = object()
    presenter._last_img_sig = object()
    presenter._cached_base_pixmap = object()
    presenter.current_displayed_pixmap = object()
    presenter._pending_interactive_mode = None
    presenter._pending_cached_diff_request_key = "k"

    ic_lifecycle.invalidate_render_state(presenter)

    assert manager.closed == [77]
    assert presenter._active_diff_toast_id is None
    assert presenter._active_diff_toast_key is None
