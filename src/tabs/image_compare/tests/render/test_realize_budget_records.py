"""Phase B2 (ic-residency-bus): realize path populates frame-bus BudgetStats.

Pins that the realize path fills ``BudgetStats`` budget/deadline fields
with *measured* values (live module globals, not literals) and records
them through ``FrameContext.record`` only:

* ``realize_tile_plan`` records pass ``"realize_tile_plan"`` with full
  counts (uploaded/skipped measured from pre/post residency snapshots,
  time measured around the shared loop);
* ``realize_main_tiles`` / ``realize_magnifier_tiles`` record branch
  passes ``"realize_main"`` / ``"realize_magnifier"`` with the same live
  budgets (branch duration reuses the gated tile-dump measurement);
* no context (fakes / direct callers) stays record-free AND
  behavior-identical -- eviction/budget decisions bit-for-bit the same.

Fake-widget conventions follow
``test_realize_tile_plan_budget.py`` (SimpleNamespace widget, real
``TileTextureService`` + ``RhiResources`` realizer).
"""

from __future__ import annotations

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from engine.cache.tile_texture_service import TileTextureService
from engine.frame.context import FrameContext
from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources
from tabs.image_compare.canvas.rhi_renderer.use_cases import tile_residency as tile_residency_module

_PATCHED_COUNT_BUDGET = 2
_PATCHED_TIME_BUDGET_MS = 1234.5


def _tps(image: Image.Image, tmp_path) -> TiledPixelStore:
    return TiledPixelStore.from_pil(image, tmp_dir=str(tmp_path))


def _widget(*, stored0, update_calls: list):
    state = SimpleNamespace(
        _pending_texture_uploads=[],
        _images_uploaded=[False, False],
        _texture_upload_cache=OrderedDict(),
        _qimage_by_uid_cache=OrderedDict(),
        _stored_pil_images=[None, None],
        _stored_image_ids=None,
        _source_pil_images=[None, None],
        _source_image_ids=None,
        _source_images_ready=False,
        _shader_letterbox_mode=False,
        _letterbox_params=[None, None],
        _content_rect_px=None,
        _inner_content_rect_px=None,
        _clip_overlays_to_content_rect=False,
        _host_texture_upload_cache=None,
    )
    widget = SimpleNamespace(
        runtime_state=state,
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        width=lambda: 800,
        height=lambda: 600,
        update=lambda: update_calls.append(1),
    )
    from tabs.image_compare.canvas.texture_parts.base_images import upload_pil_images

    upload_pil_images(widget, stored0, stored0, shader_letterbox=True)
    return widget


def _widget_with_context(*, stored0, update_calls: list):
    widget = _widget(stored0=stored0, update_calls=update_calls)
    frame_context = FrameContext()
    widget._rhi_renderer = SimpleNamespace(frame_context=frame_context)
    return widget, frame_context


def _resources():
    resources = RhiResources()
    resources.rhi = MagicMock()
    resources.textures = {}
    resources.texture_sizes = {}
    resources.upload_whole = MagicMock()
    return resources


def _base_image():
    return SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
    )


def _patch_budgets(monkeypatch):
    from engine.cache import residency as shared_residency_module
    from engine.cache import tile_upload_budget as upload_budget_module

    monkeypatch.setattr(
        shared_residency_module, "TILE_UPLOAD_BUDGET_PER_CALL", _PATCHED_COUNT_BUDGET
    )
    monkeypatch.setattr(
        upload_budget_module, "TILE_UPLOAD_TIME_BUDGET_MS", _PATCHED_TIME_BUDGET_MS
    )


def _records_by_pass(frame_context, pass_name):
    return [d for d in frame_context if d.pass_name == pass_name]


def _stats_tuple(decision):
    # ids schema: (frame_tag, keys_tuple, BudgetStats.as_tuple()).
    assert len(decision.ids) == 3
    return decision.ids[2]


def test_realize_tile_plan_records_measured_budgets(tmp_path, monkeypatch):
    _patch_budgets(monkeypatch)
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget, frame_context = _widget_with_context(
        stored0=store, update_calls=update_calls
    )
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)

    more_pending = resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), _base_image(), MagicMock()
    )

    decisions = _records_by_pass(frame_context, "realize_tile_plan")
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.verdict == ("skipped" if more_pending else "ran")
    assert more_pending, "1200x800 (6 tiles/key) must exceed the patched budget of 2"
    budget, uploaded, skipped, time_ms, budget_ms, pending = _stats_tuple(decision)
    # Measured, not placeholders: the patched live globals flow through.
    assert budget == _PATCHED_COUNT_BUDGET
    assert budget_ms == _PATCHED_TIME_BUDGET_MS
    assert pending is True
    # Full counts measured from pre/post residency snapshots.
    assert uploaded > 0
    assert skipped > 0
    assert isinstance(time_ms, float) and time_ms >= 0.0
    assert f"budget={_PATCHED_COUNT_BUDGET}" in decision.reason


def test_realize_tile_plan_without_context_is_identical(tmp_path, monkeypatch):
    """No context (direct test callers, fakes) records nothing and changes
    nothing: same return, same resident sets as the context-carrying call."""
    _patch_budgets(monkeypatch)
    updates = MagicMock()

    store_a = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    widget_a = _widget(stored0=store_a, update_calls=[])
    resources_a = _resources()
    service_a = TileTextureService(max_tile_extent=512)
    pending_a = resources_a.residency.realize_tile_plan(
        service_a, widget_a, ("stored_0", "stored_1"), _base_image(), updates
    )

    store_b = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls_b: list = []
    widget_b, frame_context_b = _widget_with_context(
        stored0=store_b, update_calls=update_calls_b
    )
    resources_b = _resources()
    service_b = TileTextureService(max_tile_extent=512)
    pending_b = resources_b.residency.realize_tile_plan(
        service_b, widget_b, ("stored_0", "stored_1"), _base_image(), updates
    )

    assert pending_a == pending_b
    for key in ("stored_0", "stored_1"):
        assert service_a.resident_tiles(key) == service_b.resident_tiles(key)
    # The context call recorded exactly one realize fact; the
    # context-free call recorded nothing anywhere (no context, no crash).
    assert len(_records_by_pass(frame_context_b, "realize_tile_plan")) == 1


def test_realize_main_wrapper_records_branch_fact(tmp_path, monkeypatch):
    _patch_budgets(monkeypatch)
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget, frame_context = _widget_with_context(
        stored0=store, update_calls=update_calls
    )
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    renderer = SimpleNamespace(
        _last_good_texture_keys=(),
        _last_good_diff_key=None,
        tile_service=tile_service,
        resources=resources,
    )

    main_more_pending = tile_residency_module.realize_main_tiles(
        renderer,
        widget,
        ("stored_0", "stored_1"),
        _base_image(),
        MagicMock(),
        None,
        None,
        None,
        {},
    )

    assert main_more_pending is True
    main_decisions = _records_by_pass(frame_context, "realize_main")
    assert len(main_decisions) == 1
    budget, _uploaded, _skipped, _time_ms, budget_ms, pending = _stats_tuple(
        main_decisions[0]
    )
    assert budget == _PATCHED_COUNT_BUDGET
    assert budget_ms == _PATCHED_TIME_BUDGET_MS
    assert pending is True
    assert main_decisions[0].verdict == "skipped"
    # The inner realize_tile_plan call recorded its own full-count fact.
    plan_decisions = _records_by_pass(frame_context, "realize_tile_plan")
    assert len(plan_decisions) == 1
    assert _stats_tuple(plan_decisions[0])[1] > 0  # uploaded measured


def test_realize_magnifier_wrapper_records_when_branch_active(
    tmp_path, monkeypatch
):
    _patch_budgets(monkeypatch)
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget, frame_context = _widget_with_context(
        stored0=store, update_calls=update_calls
    )
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    renderer = SimpleNamespace(
        _last_good_texture_keys=(),
        _last_good_diff_key=None,
        tile_service=tile_service,
        resources=resources,
    )
    overlay = SimpleNamespace(gpu_active=True, gpu_slots=[])
    ctx = SimpleNamespace(
        feature_overlay=overlay,
        source_texture_ids=("source_0", "source_1"),
        source_images_ready=True,
        diff_source_texture_id=None,
        diff_source_ready=False,
    )

    tile_residency_module.realize_magnifier_tiles(
        renderer,
        widget,
        ctx,
        ("stored_0", "stored_1"),
        _base_image(),
        MagicMock(),
        None,
        None,
        {},
    )

    mag_decisions = _records_by_pass(frame_context, "realize_magnifier")
    assert len(mag_decisions) == 1
    budget, _u, _s, _t, budget_ms, _p = _stats_tuple(mag_decisions[0])
    assert budget == _PATCHED_COUNT_BUDGET
    assert budget_ms == _PATCHED_TIME_BUDGET_MS


def test_realize_magnifier_wrapper_silent_when_branch_inactive(tmp_path):
    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget, frame_context = _widget_with_context(
        stored0=store, update_calls=update_calls
    )
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)
    renderer = SimpleNamespace(
        _last_good_texture_keys=(),
        _last_good_diff_key=None,
        tile_service=tile_service,
        resources=resources,
    )
    # Same keys as the canvas call + no overlay: branch inactive, no
    # realize work, hence no magnifier record.
    ctx = SimpleNamespace(
        feature_overlay=None,
        source_texture_ids=("stored_0", "stored_1"),
        source_images_ready=False,
        diff_source_texture_id=None,
        diff_source_ready=False,
    )

    tile_residency_module.realize_magnifier_tiles(
        renderer,
        widget,
        ctx,
        ("stored_0", "stored_1"),
        _base_image(),
        MagicMock(),
        None,
        None,
        {},
    )

    assert _records_by_pass(frame_context, "realize_magnifier") == []
    assert _records_by_pass(frame_context, "realize_tile_plan") == []


def test_production_budgets_flow_through_unpatched(tmp_path):
    """Without monkeypatching, the record carries the live production
    constants -- guards against hardcoded placeholder literals."""
    from engine.cache import residency as shared_residency_module
    from engine.cache import tile_upload_budget as upload_budget_module

    store = _tps(Image.new("RGBA", (1200, 800), "blue"), tmp_path)
    update_calls: list = []
    widget, frame_context = _widget_with_context(
        stored0=store, update_calls=update_calls
    )
    resources = _resources()
    tile_service = TileTextureService(max_tile_extent=512)

    resources.residency.realize_tile_plan(
        tile_service, widget, ("stored_0", "stored_1"), _base_image(), MagicMock()
    )

    decisions = _records_by_pass(frame_context, "realize_tile_plan")
    assert len(decisions) == 1
    budget, _u, _s, _t, budget_ms, _p = _stats_tuple(decisions[0])
    assert budget == shared_residency_module.TILE_UPLOAD_BUDGET_PER_CALL
    assert budget_ms == upload_budget_module.TILE_UPLOAD_TIME_BUDGET_MS
