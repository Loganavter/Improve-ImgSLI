"""Multi Compare must show a "loading full version of image" toast during
full-res decode + pyramid build, mirroring image_compare's
_session_controller (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up
investigation surfaced that multi_compare never had this feedback at all).
"""

from types import SimpleNamespace

from PIL import Image

from tabs.multi_compare.controller import MultiCompareController


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list[tuple[int, str, dict]] = []
        self.updated: list[tuple[int, str, dict]] = []
        self.closed: list[int] = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _FakeThreadPool:
    """Runs a GenericWorker synchronously -- run() itself is synchronous
    (see sli_ui_toolkit.workers.generic_worker.GenericWorker.run), so no
    real threading/event loop is needed for the signals it fires."""

    def start(self, worker):
        worker.run()


def _make_controller(*, thread_pool=None, main_window=None):
    widget = SimpleNamespace(
        state=SimpleNamespace(root=None, slots=[]),
        canvas=SimpleNamespace(request_view_update=lambda: None),
        images_dropped=SimpleNamespace(connect=lambda *_: None),
        add_requested=SimpleNamespace(connect=lambda *_: None),
        save_requested=SimpleNamespace(connect=lambda *_: None),
        quick_save_requested=SimpleNamespace(connect=lambda *_: None),
        settings_requested=SimpleNamespace(connect=lambda *_: None),
        help_requested=SimpleNamespace(connect=lambda *_: None),
        divider_color_picker_requested=SimpleNamespace(connect=lambda *_: None),
    )
    context = SimpleNamespace(main_window=main_window, thread_pool=thread_pool)
    store = SimpleNamespace(settings=SimpleNamespace())
    return MultiCompareController(widget, store=store, context=context)


def test_show_loading_toast_creates_toast_once():
    toast_manager = _FakeToastManager()
    controller = _make_controller(main_window=SimpleNamespace(toast_manager=toast_manager))

    controller._show_loading_toast(1)
    controller._show_loading_toast(1)  # idempotent -- must not double-show

    assert len(toast_manager.shown) == 1
    assert 1 in controller._loading_toasts


def test_mark_full_res_ready_bumps_progress():
    toast_manager = _FakeToastManager()
    controller = _make_controller(main_window=SimpleNamespace(toast_manager=toast_manager))
    controller._show_loading_toast(1)

    controller._mark_full_res_ready(1)

    _, _, kwargs = toast_manager.updated[-1]
    assert kwargs["progress"] == controller._DECODE_DONE_PROGRESS


def test_finish_loading_toast_marks_success_and_forgets_slot():
    toast_manager = _FakeToastManager()
    controller = _make_controller(main_window=SimpleNamespace(toast_manager=toast_manager))
    controller._show_loading_toast(1)

    controller._finish_loading_toast(1)

    _, _, kwargs = toast_manager.updated[-1]
    assert kwargs["success"] is True
    assert kwargs["progress"] == 100
    assert 1 not in controller._loading_toasts


def test_dismiss_loading_toast_closes_without_success_banner():
    toast_manager = _FakeToastManager()
    controller = _make_controller(main_window=SimpleNamespace(toast_manager=toast_manager))
    controller._show_loading_toast(1)

    controller._dismiss_loading_toast(1)

    assert toast_manager.closed == [1]
    assert toast_manager.updated == []
    assert 1 not in controller._loading_toasts


def test_start_pyramid_build_finishes_toast_immediately_when_no_pyramid_needed(
    tmp_path, monkeypatch
):
    toast_manager = _FakeToastManager()
    controller = _make_controller(
        thread_pool=_FakeThreadPool(),
        main_window=SimpleNamespace(toast_manager=toast_manager),
    )
    controller._show_loading_toast(1)

    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    path = tmp_path / "tiny.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(path)
    store = TiledPixelStore.from_path(str(path))

    monkeypatch.setattr(
        "shared.image_processing.pyramid_registry.ensure_pyramid", lambda _store: None
    )

    controller._start_pyramid_build(store, slot_id=1)

    assert 1 not in controller._loading_toasts
    _, _, kwargs = toast_manager.updated[-1]
    assert kwargs["success"] is True


def test_start_pyramid_build_tracks_progress_and_completes(tmp_path, monkeypatch):
    toast_manager = _FakeToastManager()
    controller = _make_controller(
        thread_pool=_FakeThreadPool(),
        main_window=SimpleNamespace(toast_manager=toast_manager),
    )
    controller._show_loading_toast(1)

    from shared.image_processing.tiled_pixel_store import TiledPixelStore

    path = tmp_path / "tiny.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(path)
    store = TiledPixelStore.from_path(str(path))

    class _FakePyramid:
        valid = True

        def __init__(self):
            self.level_count = 0
            self._levels = 3

        def is_complete(self):
            return self.level_count >= self._levels

        def build_next_level(self, should_abort=None):
            if self.is_complete():
                return False
            self.level_count += 1
            return True

    pyramid = _FakePyramid()
    monkeypatch.setattr(
        "shared.image_processing.pyramid_registry.ensure_pyramid", lambda _store: pyramid
    )

    controller._start_pyramid_build(store, slot_id=1)

    # Bumped to the pyramid-start checkpoint before the (synchronous, in this
    # test) build ran, then progressed through each level, then finished.
    percents = [kwargs["progress"] for _, _, kwargs in toast_manager.updated]
    assert percents[0] == controller._PYRAMID_START_PROGRESS
    assert percents[-1] == 100
    assert toast_manager.updated[-1][2]["success"] is True
    assert 1 not in controller._loading_toasts