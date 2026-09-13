"""Skipped/aborted unify still feeds pyramid builds for decoded sides.

Regression: a unify task skipped by the preview-tier guard returns no
pair, so the normal ``_start_pyramid_builds(u1, u2)`` never runs — and the
loading toast waits for pyramid completions nobody builds (stall). Now the
early exits start builds for the full-res sides already decoded; preview
or missing sides are skipped positionally, their full arrival re-triggers
unify via ``handle_full_image_loaded``.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from tabs.image_compare.use_cases import unify as _unify


class _Coord:
    def __init__(self):
        self.calls = []

    def start_build(self, store, *, slot_id=None, **kw):
        self.calls.append((store, slot_id))
        return True


def _controller(*, peek_map, coordinator=None):
    coord = coordinator if coordinator is not None else _Coord()
    calls = {"builds": []}

    def _start(*stores):
        from tabs.image_compare.use_cases.loading_pyramid import start_pyramid_builds

        class _C:
            pipeline = None
            _pyramid_coordinator = coord

            def _get_image_session(self):
                return None

        start_pyramid_builds(_C(), *stores)
        calls["builds"].append(tuple(stores))

    pipeline = SimpleNamespace(
        peek=lambda path: peek_map.get(path),
        _inflight={},
    )
    document = SimpleNamespace(image1_path="p1", image2_path="p2")
    store = SimpleNamespace(
        viewport=SimpleNamespace(session_data=SimpleNamespace(render_cache=None)),
        get_dispatcher=lambda: None,
        get_session_state_slot=lambda name: document if name == "document" else None,
    )
    metrics = SimpleNamespace(on_metrics_calculated=lambda v: calls.setdefault("metrics", []).append(v))
    controller = SimpleNamespace(
        store=store,
        pipeline=pipeline,
        metrics_service=metrics,
        _start_pyramid_builds=_start,
        _calls=calls,
        _coord=coord,
    )
    return controller


def _tps():
    return SimpleNamespace(is_open=True)


def test_none_result_starts_builds_for_full_sides_only():
    full1 = _tps()
    controller = _controller(peek_map={"p1": full1, "p2": None})
    _unify.on_unified_images_ready(controller, None)
    assert controller._calls["builds"] == [(full1, None)]
    assert controller._coord.calls == [(full1, 1)]
    assert controller._calls["metrics"] == [None]


def test_none_result_with_nothing_ready_starts_nothing():
    controller = _controller(peek_map={})
    _unify.on_unified_images_ready(controller, None)
    assert controller._calls["builds"] == []
    assert controller._calls["metrics"] == [None]


def test_qimage_side_never_starts_build():
    preview = QImage(32, 32, QImage.Format.Format_RGBA8888)
    controller = _controller(peek_map={"p1": preview, "p2": None})
    _unify.on_unified_images_ready(controller, None)
    assert controller._calls["builds"] == []


def test_loading_start_skips_none_positionally():
    coord = _Coord()
    controller = _controller(peek_map={}, coordinator=coord)
    from tabs.image_compare.use_cases.loading_pyramid import start_pyramid_builds

    class _C:
        pipeline = None
        _pyramid_coordinator = coord

        def _get_image_session(self):
            return None

    start_pyramid_builds(_C(), None, _tps())
    assert len(coord.calls) == 1
    assert coord.calls[0][1] == 2
