"""Progressive full-resolution worker results are delivered through QObject methods."""

from types import SimpleNamespace

from tabs.image_compare._session_controller import SessionController
from tabs.image_compare.use_cases.loading import on_unified_images_ready


def test_full_resolution_result_adapter_forwards_worker_payload():
    controller = SessionController.__new__(SessionController)
    calls = []
    controller._on_full_image_loaded = lambda *args: calls.append(args)
    image = object()

    controller._on_full_resolution_loaded_result(
        (image, "/tmp/image.png", 2, 7)
    )

    assert calls == [(image, "/tmp/image.png", 2, 7)]


def test_full_resolution_result_adapter_rejects_invalid_payload():
    controller = SessionController.__new__(SessionController)
    calls = []
    controller._on_full_image_loaded = lambda *args: calls.append(args)

    controller._on_full_resolution_loaded_result(None)
    controller._on_full_resolution_loaded_result((object(), "path"))

    assert calls == []


def test_successful_unification_clears_pending_paths():
    from tabs.image_compare.pipeline.abort import AbortSignal

    image1 = object()
    image2 = object()
    render_cache = SimpleNamespace(
        unification_in_progress=True,
        pending_unification_paths=("left.png", "right.png"),
        cached_diff_image=None,
    )
    document = SimpleNamespace(
        image1_path="left.png",
        image2_path="right.png",
    )
    store = SimpleNamespace(
        get_session_state_slot=lambda name: document if name == "document" else None,
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                render_cache=render_cache,
                image_state=SimpleNamespace(image1=None, image2=None),
            ),
            render_config=SimpleNamespace(),
        ),
        invalidate_render_cache=lambda: None,
        get_dispatcher=lambda: None,
        emit_state_change=lambda *_a, **_k: None,
        batch_changes=lambda: SimpleNamespace(__enter__=lambda *_a: None, __exit__=lambda *_a: False),
        invalidate_geometry_cache=lambda: None,
    )
    # minimal dispatcher mock for _clear_unification_flags
    class _Dispatcher:
        def dispatch(self, action, scope=None):
            if hasattr(action, "enabled"):
                render_cache.unification_in_progress = bool(action.enabled)
            if hasattr(action, "paths"):
                render_cache.pending_unification_paths = action.paths
            if hasattr(action, "value"):
                pass
    store.get_dispatcher = lambda: _Dispatcher()
    # batch_changes context
    from contextlib import contextmanager

    @contextmanager
    def _batch():
        yield

    store.batch_changes = _batch
    signal = AbortSignal()
    controller = SimpleNamespace(
        _start_pyramid_builds=lambda *stores: None,
        store=store,
        diff_service=None,
        metrics_service=SimpleNamespace(on_metrics_calculated=lambda value: None),
        _invalidate_image_canvas_render_state=lambda **kwargs: None,
        _schedule_image_canvas_update=lambda: None,
        _trigger_metrics_calculation_if_needed=lambda: None,
        event_bus=None,
        update_requested=SimpleNamespace(emit=lambda: None),
        presenter=None,
        pipeline=SimpleNamespace(cache=SimpleNamespace(put_unified=lambda *a, **k: None), peek=lambda p: None, peek_preview=lambda p: None),
    )

    on_unified_images_ready(
        controller,
        (image1, image2, "left.png", "right.png", signal),
    )

    assert render_cache.unification_in_progress is False
    assert render_cache.pending_unification_paths is None


def test_unified_ready_after_session_switch_does_not_crash():
    """Worker can finish after Move/tab switch left a bare SessionData."""
    from tabs.image_compare.pipeline.abort import AbortSignal

    store = SimpleNamespace(
        get_session_state_slot=lambda _name: None,
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(render_cache=None, image_state=None),
        ),
    )
    metrics = []
    controller = SimpleNamespace(
        store=store,
        metrics_service=SimpleNamespace(
            on_metrics_calculated=lambda value: metrics.append(value)
        ),
        pipeline=SimpleNamespace(cache=SimpleNamespace(put_unified=lambda *a, **k: None), peek=lambda p: None, peek_preview=lambda p: None),
        _start_pyramid_builds=lambda *a, **k: None,
        _invalidate_image_canvas_render_state=lambda **k: None,
        _schedule_image_canvas_update=lambda: None,
        _trigger_metrics_calculation_if_needed=lambda: None,
        event_bus=None,
        update_requested=SimpleNamespace(emit=lambda: None),
        presenter=None,
    )
    sig = AbortSignal()
    on_unified_images_ready(
        controller,
        (object(), object(), "a.png", "b.png", sig),
    )
    on_unified_images_ready(controller, None)
    assert metrics == [None]
