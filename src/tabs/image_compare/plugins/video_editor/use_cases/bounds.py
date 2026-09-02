"""Global bounds use-case — thin owner owns state, logic lives here.

Pattern: docs/dev/CODE_PATTERNS.md#thin-owner-use_cases
Moved from presenter_parts/preview.py so PreviewCoordinator stays thin.
Coordinator methods remain as forwarders.
"""

import logging

from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")


def _next_gen(coordinator) -> int:
    # Prefer coordinator's own monotonic token; fallback to model generation
    if hasattr(coordinator, "_next_generation") and callable(getattr(coordinator, "_next_generation")):
        try:
            return coordinator._next_generation()
        except Exception:
            pass
    if hasattr(coordinator, "_bounds_request_id"):
        try:
            coordinator._bounds_request_id += 1  # type: ignore[attr-defined]
            return int(coordinator._bounds_request_id)
        except Exception:
            pass
    if hasattr(coordinator, "_generation"):
        try:
            coordinator._generation += 1  # type: ignore[attr-defined]
            # also bump model generation if present
            if getattr(coordinator, "model", None) is not None and hasattr(coordinator.model, "new_generation"):
                try:
                    coordinator.model.new_generation()
                except Exception:
                    pass
            return int(coordinator._generation)
        except Exception:
            pass
    return 0

def _current_gen(coordinator) -> int | None:
    if hasattr(coordinator, "_generation"):
        try:
            return int(coordinator._generation)
        except Exception:
            pass
    if hasattr(coordinator, "_bounds_request_id"):
        try:
            return int(coordinator._bounds_request_id)
        except Exception:
            pass
    return None

def _is_stale(coordinator, request_id: int | None) -> bool:
    if request_id is None:
        return False
    cur = _current_gen(coordinator)
    return cur is not None and request_id != cur


def recalculate_global_bounds(coordinator) -> None:
    exporter = getattr(coordinator.export_controller, "video_exporter", None)
    if exporter is None:
        return

    snapshots = coordinator.editor_service.get_current_snapshots()
    if not snapshots:
        return

    from tabs.image_compare.plugins.video_editor.presenter_parts.common import VIDEO_EDITOR_AUTO_CROP

    request_id = _next_gen(coordinator)

    def calculate():
        return exporter.calculate_global_canvas_bounds(snapshots, VIDEO_EDITOR_AUTO_CROP)

    worker = GenericWorker(calculate)
    worker.signals.result.connect(
        lambda bounds, rid=request_id: on_global_bounds_calculated(coordinator, bounds, request_id=rid)
    )
    worker.signals.error.connect(
        lambda err, rid=request_id: on_bounds_calculation_error(coordinator, err, request_id=rid)
    )
    coordinator.export_controller.thread_pool.start(worker)


def on_global_bounds_calculated(coordinator, bounds, request_id: int | None = None) -> None:
    if _is_stale(coordinator, request_id):
        return
    exporter = getattr(coordinator.export_controller, "video_exporter", None)
    # Store in Service cache (single source) and keep coordinator mirror for compat
    if exporter is not None:
        try:
            exporter.store_cached_global_bounds(bounds, coordinator.editor_service.get_current_snapshots())  # type: ignore[attr-defined]
        except AttributeError:
            try:
                exporter._cached_global_bounds = bounds  # type: ignore[attr-defined]
            except Exception:
                pass
    # Keep coordinator's own cache in sync (older preview stored locally)
    try:
        coordinator._cached_global_bounds = bounds  # type: ignore[attr-defined]
    except Exception:
        pass

    if coordinator.emit_fit_content_available is not None:
        try:
            coordinator.emit_fit_content_available(bounds is None or bounds.extends_beyond_unit())
        except Exception:
            pass

    if bounds and getattr(coordinator, "fit_content_mode", False) and coordinator.has_live_view():
        g_pad_left = int(bounds.pad_left)
        g_pad_right = int(bounds.pad_right)
        g_pad_top = int(bounds.pad_top)
        g_pad_bottom = int(bounds.pad_bottom)
        g_base_w = int(bounds.base_width)
        g_base_h = int(bounds.base_height)
        canvas_w = g_base_w + g_pad_left + g_pad_right
        canvas_h = g_base_h + g_pad_top + g_pad_bottom

        coordinator.view.blockSignals(True)
        was_locked = coordinator.model.aspect_ratio_locked
        coordinator.model.aspect_ratio_locked = False
        coordinator.model.set_resolution(canvas_w, canvas_h)
        coordinator.model.aspect_ratio_locked = was_locked
        coordinator.view.set_resolution(canvas_w, canvas_h)
        coordinator.view.blockSignals(False)

    try:
        coordinator.schedule_update()
    except Exception:
        pass


def on_bounds_calculation_error(coordinator, err, request_id: int | None = None) -> None:
    if _is_stale(coordinator, request_id):
        return
    logger.error(f"Error calculating global bounds: {err}")
    if coordinator.emit_fit_content_available is not None:
        try:
            coordinator.emit_fit_content_available(True)
        except Exception:
            pass
