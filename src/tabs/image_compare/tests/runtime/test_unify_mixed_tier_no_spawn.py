"""Mixed-tier unify must not spawn empty workers (nor eat the retry).

Regression (queue task-ic-unify-mixed-tier-2026-09-13): with one side still
preview-tier (QImage 1024) and the other full-res (TiledPixelStore 5760),
``ensure_unification`` spawned a GenericWorker whose ``unify_pair`` aborted
inside the worker (preview-tier guard) — an empty task. The path-only
``_inflight`` dedup key plus the still-set ``unification_in_progress`` flag
then swallowed the post-full-load retry (second ``get_unified`` miss with
no new task).

Contract under test:
- mixed QImage + full store spawns ZERO workers and only builds ready sides;
- after the second side goes full, ``ensure_unification`` spawns EXACTLY
  one task (dedup key carries uid/tier, skipped path clears the flag).
"""

from __future__ import annotations

import contextlib
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.use_cases import unify as _unify


def _full_store(width=64, height=48):
    return SimpleNamespace(width=width, height=height, is_open=True)


def _controller(*, pixel_map, preview_map):
    calls = {"starts": [], "builds": [], "dispatched": []}
    render_cache = SimpleNamespace(
        unification_in_progress=False, pending_unification_paths=None
    )
    document = SimpleNamespace(image1_path="p1", image2_path="p2")
    viewport = SimpleNamespace(
        session_data=SimpleNamespace(
            image_state=SimpleNamespace(image1=None, image2=None),
            render_cache=render_cache,
        ),
        render_config=SimpleNamespace(interpolation_method="LANCZOS"),
    )

    def _dispatch(action, scope=None):
        calls["dispatched"].append(action)
        if hasattr(action, "enabled"):
            render_cache.unification_in_progress = bool(action.enabled)
        if hasattr(action, "paths"):
            render_cache.pending_unification_paths = action.paths

    pipeline = SimpleNamespace(
        peek=lambda path: pixel_map.get(path),
        peek_preview=lambda path: preview_map.get(path),
        cache=PipelineCache(),
        _inflight={},
    )
    store = SimpleNamespace(
        viewport=viewport,
        get_dispatcher=lambda: SimpleNamespace(dispatch=_dispatch),
        batch_changes=lambda: contextlib.nullcontext(),
        get_session_state_slot=lambda name: document if name == "document" else None,
        invalidate_render_cache=lambda: None,
    )

    def _start_builds(*stores):
        calls["builds"].append(tuple(stores))

    controller = SimpleNamespace(
        store=store,
        pipeline=pipeline,
        metrics_service=SimpleNamespace(on_metrics_calculated=lambda v: None),
        thread_pool=SimpleNamespace(start=lambda worker, **kw: calls["starts"].append(worker)),
        _unify_images_worker_task=lambda *a, **k: None,
        _on_unified_images_ready=lambda result: None,
        _start_pyramid_builds=_start_builds,
        _calls=calls,
    )
    return controller


def test_mixed_tier_spawns_no_worker_and_builds_ready_side_only():
    preview = QImage(32, 24, QImage.Format.Format_RGBA8888)
    full2 = _full_store()
    controller = _controller(pixel_map={"p2": full2}, preview_map={"p1": preview})

    _unify.ensure_unification(controller)

    assert controller._calls["starts"] == []
    # ready sides served without a worker: slot1 preview skipped, slot2 built
    assert controller._calls["builds"] == [(None, full2)]
    assert controller.store.viewport.session_data.render_cache.unification_in_progress is False


def test_full_full_after_mixed_spawns_exactly_one_task():
    preview = QImage(32, 24, QImage.Format.Format_RGBA8888)
    full1 = _full_store()
    full2 = _full_store()
    pixel_map = {"p2": full2}
    controller = _controller(pixel_map=pixel_map, preview_map={"p1": preview})

    _unify.ensure_unification(controller)
    assert controller._calls["starts"] == []

    # second side goes full (preview replaced by decoded store)
    pixel_map["p1"] = full1
    _unify.ensure_unification(controller)

    assert len(controller._calls["starts"]) == 1
    # dedup key must carry identity/tier, not bare paths — a stale
    # path-only entry from the skipped pass must not suppress the retry
    assert len(controller.pipeline._inflight) == 1
    (key,) = list(controller.pipeline._inflight.keys())
    assert key != ("p1", "p2", "LANCZOS")
    assert controller.store.viewport.session_data.render_cache.unification_in_progress is True
