"""Canvas invalidation — extracted from _session_controller.py (Phase 4).

Thin-owner pattern (CODE_PATTERNS.md:161 MethodObject split):
controller stays forwarder + ui_batcher + ImageSession, logic lives here
as plain functions taking controller as first arg.
"""

from __future__ import annotations

def invalidate_image_canvas_render_state(controller, clear_overlay_state: bool = False) -> None:
    # Hang fix: previous coalesce introduced infinite loop —
    # _flush → presenter.invalidate → store change → resync → set_current →
    # _invalidate → schedule → loop every event-loop turn. Keep immediate
    # invalidate (synchronous) but break re-entrancy and throttle log.
    if getattr(controller, "_invalidating", False):
        if clear_overlay_state:
            controller._pending_clear_overlay = True  # type: ignore[attr-defined]
        return
    controller._invalidating = True  # type: ignore[attr-defined]
    try:
        import time

        now = time.monotonic()
        last = getattr(controller, "_last_invalidate_log_ts", 0.0)
        should_log = (now - last) > 0.2
        pending_clear = bool(getattr(controller, "_pending_clear_overlay", False))
        clear = bool(clear_overlay_state or pending_clear)
        controller._pending_clear_overlay = False  # type: ignore[attr-defined]
        if should_log:
            from tabs.image_compare.debug import ic_preview_debug as _preview_log

            _preview_log(
                "render state invalidated (clear_overlay=%s)",
                clear,
            )
            controller._last_invalidate_log_ts = now  # type: ignore[attr-defined]
        presenter = getattr(controller, "presenter", None)
        if presenter and hasattr(presenter, "invalidate_canvas_render_state"):
            presenter.invalidate_canvas_render_state(clear_overlay_state=clear)
        if clear:
            try:
                canvas_widget = None
                if presenter is not None:
                    w = getattr(presenter, "widget", None)
                    if w is not None:
                        canvas_widget = getattr(w, "image_label", None)
                        if canvas_widget is None:
                            from tabs.image_compare.canvas.helpers import get_canvas

                            canvas_widget = get_canvas(w)
                if canvas_widget is not None and hasattr(canvas_widget, "runtime_state"):
                    rs = canvas_widget.runtime_state
                    rs._stored_image_ids = None
                    rs._stored_pil_images = [None, None]
                    rs._source_pil_images = [None, None]
                    rs._source_image_ids = None
                    rs._source_images_ready = False
                    rs._content_rect_px = None
                    rs._inner_content_rect_px = None
                    rs._inner_split_position = None
                    rs._letterbox_params = [None, None]
                    rs._images_uploaded = [False, False]
                    rs._shader_letterbox_mode = False
                    rs._content_sr = 1.0
                    rs._clip_overlays_to_content_rect = False
            except Exception:
                pass
    finally:
        controller._invalidating = False  # type: ignore[attr-defined]
        if getattr(controller, "_pending_clear_overlay", False):
            controller._pending_clear_overlay = False  # type: ignore[attr-defined]
            invalidate_image_canvas_render_state(controller, clear_overlay_state=True)


def schedule_image_canvas_update(controller) -> None:
    presenter = getattr(controller, "presenter", None)
    if presenter and hasattr(presenter, "schedule_canvas_update"):
        try:
            presenter.schedule_canvas_update()
        except Exception:
            pass
