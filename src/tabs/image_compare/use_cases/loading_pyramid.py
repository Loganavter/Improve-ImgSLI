"""Image pyramid builds: spawn workers, track progress, update canvas.

The pyramid provides tiled LOD (level-of-detail) for GPU rendering.
Each full-res image store gets a pyramid that builds progressively in
a background worker, emitting per-level progress signals.

Toast progress is managed via the controller's bound methods
(``controller._finish_loading_toast``, etc.) — the dependency is
one-directional: **pyramid --> toast** (see ``loading_toast.py``).
"""

from __future__ import annotations

import logging

from tabs.image_compare.debug import ic_preview_debug as _preview_log

logger = logging.getLogger("ImproveImgSLI")


def _has_inflight_for_slot(pipeline, image_number: int) -> bool:
    try:
        if pipeline is None or not hasattr(pipeline, "_inflight"):
            return False
        for k, sig in list(pipeline._inflight.items()):
            try:
                if sig.is_aborted():
                    continue
            except Exception:
                pass
            if isinstance(k, tuple) and len(k) >= 2 and isinstance(k[0], int) and k[0] == int(image_number):
                return True
            if isinstance(k, tuple) and k and k[0] == "__full_count__" and len(k) > 1 and k[1] == int(image_number):
                try:
                    if not sig.is_aborted():
                        return True
                except Exception:
                    return True
        return False
    except Exception:
        return False


def start_pyramid_builds(controller, *stores) -> None:
    # Called as start_pyramid_builds(controller, u1, u2) -- positional order
    # matches image_state.image1/image2 at the call site, so slot number is
    # simply the 1-based position here.
    # Prefer shared coordinator when present (B3 dedup); fallback keeps fake
    # controllers without coordinator working.
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        sess = None
        try:
            if hasattr(controller, "_get_image_session"):
                sess = controller._get_image_session()
        except Exception:
            sess = None
        abort_sig = getattr(sess, "abort", None) if sess is not None else None
        # abort signal is single source; fallback to never-aborted signal for fakes
        try:
            from tabs.image_compare.pipeline.abort import AbortSignal as _AbortSignal

            if abort_sig is None or not hasattr(abort_sig, "is_aborted"):
                abort_sig = _AbortSignal()
        except Exception:
            abort_sig = None
        for slot_offset, store in enumerate(stores):
            image_number = slot_offset + 1
            # toast liveness via single-flight: no pending full decode for slot
            pl = getattr(controller, "pipeline", None)
            has_inflight = _has_inflight_for_slot(pl, int(image_number))
            slot_toast_live = not has_inflight
            if abort_sig is not None and hasattr(abort_sig, "is_aborted"):
                should_abort = abort_sig.is_aborted  # type: ignore[assignment]
            else:
                should_abort = lambda: False  # type: ignore[assignment]
            # coordinator handles skip->finish, already-in-flight, bump, worker.
            # The slot is always mapped so a later complete finds its toast
            # even if the decode lands after the pyramid; toast_live gates
            # only progress bumps and skip-path finishes (preview-tier race
            # must not close a toast whose real decode is still pending).
            coord.start_build(
                store,
                slot_id=image_number,
                toast_live=slot_toast_live,
                should_abort=should_abort,
            )
        return


def on_pyramid_level_ready(controller, payload) -> None:
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        coord.on_level_ready(payload)
        return
    from tabs._shared.loading_toast import PYRAMID_START_PROGRESS

    uid, level_count, total_levels, complete = payload
    # Tile replacement marker: the pyramid just wrote a LOD level into the
    # store that backs the live canvas. Only `complete` drops the pick
    # signatures (preview -> store flip); intermediate levels only arm a
    # repaint, which render_flow then gates on its signatures.
    _preview_log(
        "tiles replaced: pyramid level ready (uid=%s level=%d/%d complete=%s)",
        uid,
        level_count,
        total_levels,
        complete,
    )
    # Only a *completed* pyramid can flip pick_display_image from the
    # preview tier to the tiled store — that's the only publish that
    # needs the pick signatures dropped. Intermediate levels just need
    # a repaint so the per-frame LOD selector can use them; a full
    # invalidation per level caused plan re-applies mid-interaction
    # (docs/dev/rendering/display-image-pipeline.md, preview→store flip).
    if complete:
        controller._invalidate_image_canvas_render_state()
    controller._schedule_image_canvas_update()
    image_number = controller._loading_toast_uid_slot.get(uid)
    if image_number is None:
        return
    if complete:
        controller._loading_toast_uid_slot.pop(uid, None)
        controller._finish_loading_toast(image_number)
    else:
        fraction = level_count / max(total_levels, 1)
        percent = PYRAMID_START_PROGRESS + int(
            fraction * (100 - PYRAMID_START_PROGRESS)
        )
        controller._set_loading_toast_progress(image_number, percent)
