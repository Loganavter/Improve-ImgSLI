"""Multi Compare decode single-flight + never-silent (A2).

Preview-stage single-flight keyed ``(normpath, mtime, size)`` (IC
``ImageLoadService`` parity): a double Add of the same file starts ONE
preview decode fanned out to both slots; the full-res second stage stays
per-slot workers but bounded (``_FULL_MAX_CONCURRENT`` FIFO). B1: decoded
tiers land in the session pixel cache — same-path slots share the one
cached store object (the cache owns the lifecycle, so sharing can never
break undo), asserted below.

Never-silent invariant: every accepted entry lands a slot or an
error-toast — nothing vanishes quietly. Orphan deliveries
(remove-before-ready) stay clean: no toast-done, no error-toast, no
crash, no touch of a recycled id.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.tests.plugins import (
    test_mc_async_first_image_load as _base,
)
from tabs.multi_compare.use_cases import loading as loading_use_cases
from tabs.multi_compare.use_cases import preview_decode as preview_decode_use_cases


def _png(tmp_path, name="img.png", size=(800, 600)):
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


def _drain(pool, limit: int = 40) -> None:
    pool.run_all(limit=limit)


def test_double_add_same_file_single_preview_decode(tmp_path, monkeypatch):
    """Double-click Add = 1 preview decode, fanned out to both slots."""
    from shared.image_processing import progressive_loader as prog_mod
    from shared.image_processing import pixel_cache_loader as pcl_mod

    pool = _base._CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _base._make_controller(pool)
    path = _png(tmp_path)

    preview_calls: list[str] = []
    real_preview = prog_mod.load_preview_image

    def _spy_preview(path_str, **kwargs):
        preview_calls.append(path_str)
        return real_preview(path_str, **kwargs)

    full_calls: list[str] = []
    real_full = pcl_mod.load_pixel_store

    def _spy_full(path_str, **kwargs):
        full_calls.append(path_str)
        return real_full(path_str, **kwargs)

    monkeypatch.setattr(prog_mod, "load_preview_image", _spy_preview)
    monkeypatch.setattr(pcl_mod, "load_pixel_store", _spy_full)

    loading_use_cases.on_images_dropped(controller, [path], (None, True), None)
    loading_use_cases.on_images_dropped(controller, [path], (None, True), None)

    assert len(widget.state.slots) == 2
    # Single-flight: the second Add attached to the first decode.
    assert len(pool.workers) == 1

    _drain(pool)

    assert preview_calls and len(preview_calls) == 1
    # Both slots filled from the one decode (preview tier, then full tier).
    from shared.image_processing.tiled_pixel_store import TiledPixelStore
    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    assert len(widget.state.slots) == 2
    stores = set()
    for slot in widget.state.slots:
        source = resolve_slot_source(controller.pixel_cache, slot)
        assert isinstance(source, TiledPixelStore)
        assert source.is_open
        assert slot.revision == 2  # preview + full noted, pixels in cache only
        stores.add(id(source))
    # Same-path slots share the one cached store (cache-owned, undo-safe).
    assert len(stores) == 1
    # Full stage stays per-slot workers: one full decode each.
    assert len(full_calls) == 2


def test_full_stage_bounded_two_concurrent(tmp_path):
    """N-file add: at most _FULL_MAX_CONCURRENT full decodes run at once."""
    pool = _base._CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _base._make_controller(pool)
    paths = [_png(tmp_path, f"img{i}.png") for i in range(3)]

    for path in paths:
        loading_use_cases.on_images_dropped(controller, [path], (None, True), None)
    assert len(pool.workers) == 3  # distinct keys: 3 preview workers

    # Drain previews only: each preview fill kicks its full-res second stage.
    for _ in range(3):
        pool.run_one()
    assert len(widget.state.slots) == 3
    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    for slot in widget.state.slots:
        assert isinstance(
            resolve_slot_source(controller.pixel_cache, slot), QImage
        )

    full_started = len(pool.workers)
    queued = list(getattr(controller, "_mc_full_queue", []))
    assert full_started == preview_decode_use_cases._FULL_MAX_CONCURRENT
    assert len(queued) == 3 - preview_decode_use_cases._FULL_MAX_CONCURRENT

    _drain(pool)
    assert getattr(controller, "_mc_full_queue", []) == []
    assert getattr(controller, "_mc_full_active", {}) == {}
    from shared.image_processing.tiled_pixel_store import TiledPixelStore
    from tabs.multi_compare.pipeline.cache import resolve_slot_source as _resolve

    for slot in widget.state.slots:
        assert isinstance(_resolve(controller.pixel_cache, slot), TiledPixelStore)


def test_remove_before_ready_no_done_no_crash(tmp_path):
    """Orphan (remove-mid-load): silent dismiss — no toast-done, no bus error."""
    for via_controller in (True, False):
        pool = _base._CapturingPool()
        controller, widget, mc_store, toast_manager, event_bus = _base._make_controller(pool)
        path = _png(tmp_path)

        loading_use_cases.on_images_dropped(controller, [path], (None, True), None)
        assert len(widget.state.slots) == 1
        if via_controller:
            controller.remove_slot(0)  # cancel-on-remove entry point
        else:
            # Widget-direct path (no eager cancel): stale guards must hold.
            widget.store.dispatch(mc_actions.remove_slot(0))

        _drain(pool)  # late worker lands after removal

        assert widget.state.slots == []
        done_banners = [
            u for u in toast_manager.updated if u[2].get("success") is True
        ]
        assert done_banners == []
        assert event_bus.emitted == []
        assert 0 not in controller._loading_toasts


def test_never_silent_corrupt_file(tmp_path):
    """Corrupt entry → no slot left behind AND an error-toast via the bus."""
    pool = _base._CapturingPool()
    controller, widget, mc_store, toast_manager, event_bus = _base._make_controller(pool)
    bad = tmp_path / "garbage.png"
    bad.write_bytes(b"not an image at all" * 64)

    loading_use_cases.on_images_dropped(controller, [bad], (None, True), None)
    assert len(widget.state.slots) == 1  # imageless slot first (P2 shape)
    _drain(pool)

    assert widget.state.slots == []
    assert len(event_bus.emitted) == 1
    err_text = str(getattr(event_bus.emitted[0], "error", event_bus.emitted[0]))
    assert "garbage.png" in err_text


def test_stale_full_res_never_finishes_orphan_toast(tmp_path):
    """Late full-res for a removed slot dismisses — never toast-done."""
    pool = _base._CapturingPool()
    controller, widget, mc_store, toast_manager, _ = _base._make_controller(pool)
    path = _png(tmp_path)

    loading_use_cases.on_images_dropped(controller, [path], (None, True), None)
    pool.run_one()  # preview lands → full-res worker queued
    from tabs.multi_compare.pipeline.cache import resolve_slot_source as _resolve2

    assert isinstance(_resolve2(controller.pixel_cache, widget.state.slots[0]), QImage)

    widget.store.dispatch(mc_actions.remove_slot(0))
    _drain(pool)  # late full-res lands after removal

    assert widget.state.slots == []
    done_banners = [
        u for u in toast_manager.updated if u[2].get("success") is True
    ]
    assert done_banners == []
