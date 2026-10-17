"""DnD overlay keep-warm / restack / show-edge timing for the IC canvas widget.

Bodies moved verbatim out of ``canvas/widget.py`` (CODE_PATTERNS thin owner +
``use_cases`` module, Part D split). Plain functions taking the widget as
their first argument; ``CanvasWidget`` keeps same-named one-line delegators so
private call sites and tests are unchanged. The DnD overlay *pass* lives next
door in ``passes.py`` / ``render/`` — this module only owns the show-edge
compositor timing that keeps drop feedback from arriving late.
"""

from __future__ import annotations

from tabs.image_compare.canvas.interaction import (
    set_drag_overlay_state as _set_drag_overlay_state_impl,
)

# DnD show-edge settle: one delayed compositor kick (drag-scoped).
# The immediate flush restacks while only the pre-tile buffer exists;
# the delayed kick lands amid presented tile-frames. Single-shot, no
# re-arm: repeated-kick and kick-weight experiments moved nothing
# visually (whole-window stall during grabs lives outside our timing),
# so this stays the minimal proven recipe (MC drag/DnD path parity).
_DND_RESTACK_DELAY_MS = 120


def _schedule_drag_restack(w) -> None:
    """Fire the delayed settle kick; no-op if the zone already hid."""
    from PySide6.QtCore import QTimer as _QTimer

    from tabs.image_compare.canvas.loupe_trace import trace_invalidation

    try:
        from tabs.image_compare.canvas.loupe_trace import (
            frame_context_from_widget as _fcw,
        )

        trace_invalidation(
            _fcw(w),
            "dnd_restack",
            f"drag restack settle kick armed delay_ms={_DND_RESTACK_DELAY_MS}",
        )
    except Exception:
        pass
    _QTimer.singleShot(_DND_RESTACK_DELAY_MS, lambda: _drag_restack_tick(w))


def _keepwarm_pending_reason(w) -> str | None:
    """Why a keep-warm tick must still prime a frame; None when idle.

    Names the pending cause so the firing tick can record *why* it could
    not stand down (``tile_more_pending``, ``fallback_more_pending``,
    ``content_swap``, ``mip_layers``, ``texture_key_mismatch``) or
    ``priming`` when renderer state is still missing (first paint —
    priming preserved by construction).
    """
    try:
        renderer = getattr(w, "_rhi_renderer", None)
        if renderer is None:
            return "priming"
        state = getattr(w, "runtime_state", None)
        if bool(getattr(state, "_tile_more_pending", False)):
            return "tile_more_pending"
        if bool(getattr(renderer, "_fallback_more_pending_snapshot", False)):
            return "fallback_more_pending"
        if bool(getattr(renderer, "_content_swap_active", False)):
            return "content_swap"
        try:
            pending = getattr(renderer, "_pending_dirty_layers", {})
            if pending and any(bool(layers) for layers in pending.values()):
                return "mip_layers"
        except Exception:
            return "priming"
        last_good = getattr(renderer, "_last_good_texture_keys", None)
        if last_good is None:
            return "priming"
        try:
            committed = getattr(renderer, "_lod_committed_keys", None)
            if committed is not None and tuple(committed) != tuple(last_good):
                return "texture_key_mismatch"
        except Exception:
            pass
        return None
    except Exception:
        return "priming"


def _drag_restack_tick(w) -> None:
    """One settle kick; stands down if the zone already hid."""
    try:
        from tabs.image_compare.debug import ic_dnd_debug as _icdd

        import time as _time

        t0 = getattr(w, "_dnd_show_t0", None)
        still = bool(w.runtime_state._drag_overlay_visible)
        _icdd(
            "canvas.restack fired +%sms still_visible=%s",
            round((_time.monotonic() - t0) * 1000) if t0 is not None else "?",
            still,
        )
        if not still:
            return
        # activate=False: external drag focus belongs to the source app —
        # raise_/activateWindow is a guaranteed-denied xdg-activation
        # request (Mutter «ожидает» banner, internal-docs inv-flyout-wayland).
        from ui.canvas_infra.rhi.rhi_present_sync import flush_qrhi_compositor

        flush_qrhi_compositor(w, reason="ic-dnd-show-settle", activate=False)
    except Exception:
        pass


def set_drag_overlay_state(
    widget,
    visible: bool,
    horizontal: bool = False,
    text1: str = "",
    text2: str = "",
) -> None:
    """Body of ``CanvasWidget.set_drag_overlay_state`` (show-edge timing)."""
    import traceback

    before = bool(widget.runtime_state._drag_overlay_visible)
    _set_drag_overlay_state_impl(widget, visible, horizontal, text1, text2)
    after = bool(widget.runtime_state._drag_overlay_visible)
    if before != after:
        try:
            from tabs.image_compare.debug import ic_dnd_debug

            ic_dnd_debug(
                "canvas.set_drag_overlay_state %s->%s visible=%s stack=%s",
                before,
                after,
                visible,
                "".join(traceback.format_stack(limit=8)[:-2]),
            )
        except Exception:
            pass
        if after and not before:
            # Mark the present counter: on hide we log how many frames
            # actually presented during the TRUE window. Tells apart
            # "no frames scheduled" from "frames recorded but dropped by
            # the compositor" without needing FIRST_FRAME_DEBUG (whose
            # sampler would itself pump frames and confound the test).
            try:
                widget._dnd_show_present_mark = int(widget._rhi_presents_completed)
            except Exception:
                widget._dnd_show_present_mark = None
            # Wall-clock show edge for the show→first-present latency probe.
            # (Per-gesture clock: reset every show, cleared on hide.)
            try:
                import time as _time

                widget._dnd_show_t0 = _time.monotonic()
            except Exception:
                widget._dnd_show_t0 = None
            try:
                widget._dnd_first_present_t = None
            except Exception:
                pass
        if before and not after:
            try:
                from tabs.image_compare.debug import ic_dnd_debug as _icdd

                import time as _time

                mark = getattr(widget, "_dnd_show_present_mark", None)
                now = int(widget._rhi_presents_completed)
                t0 = getattr(widget, "_dnd_show_t0", None)
                t_first = getattr(widget, "_dnd_first_present_t", None)
                t_now = _time.monotonic()
                if t0 is None:
                    first_ms: object = "?"
                    vis_ms: object = "?"
                else:
                    vis_ms = round((t_now - t0) * 1000)
                    first_ms = (
                        round((t_first - t0) * 1000) if t_first is not None else "never"
                    )
                _icdd(
                    "canvas.hide presents_during_show=%s visible_ms=%s first_present_ms=%s",
                    (now - mark) if mark is not None else "?",
                    vis_ms,
                    first_ms,
                )
            except Exception:
                pass
            try:
                widget._dnd_show_t0 = None
                widget._dnd_first_present_t = None
            except Exception:
                pass
        if after:
            # Wayland quirk (docs/dev/KNOWN_BUGS / qrhi-gotchas): the
            # compositor can keep showing the previous subsurface buffer
            # even though a frame with the DragDropOverlayPass tiles was
            # presented — "SSOT True, screen stale". During an external
            # drag the app additionally reports ApplicationInactive and
            # Wayland throttles the subsurface. Kick the compositor once
            # on the show edge, mirroring Multi Compare's drag/DnD path
            # and the startup first-present settle.
            try:
                from ui.canvas_infra.rhi.rhi_present_sync import (
                    flush_qrhi_compositor,
                )

                # activate=False on both kicks: external drag focus belongs
                # to the source app — activation would be denied and
                # banner (see _schedule_drag_restack below). chrome=False
                # on the immediate kick: it provably restacks the
                # pre-tile buffer (useless for tiles) while its full
                # repaint churn synchronously delays the first tile
                # frame inside the DragEnter handler — keep it light,
                # the settle chain (full kicks) does the real work.
                flush_qrhi_compositor(
                    widget, reason="ic-dnd-show", activate=False, chrome=False
                )
                # ...and once more after the first tile-frames are
                # flowing. The immediate flush above restacks while only
                # the pre-tile buffer exists; a lone restack there leaves
                # the compositor settled on stale content. The delayed
                # kick lands amid presented tile-frames. Single-shot,
                # drag-scoped; no-op if the zone already hid.
                _schedule_drag_restack(widget)
            except Exception:
                widget._request_update()


def _ensure_dnd_keepwarm(widget) -> None:
    """Idle pipeline primer: silent canvas update ticks.

    A long-static canvas shows drop feedback ~350 ms late on NVIDIA
    Wayland (cold swapchain/fences + deprioritized static surface;
    proven by bisection: 50 ms grabs+logs instant at any age, silent
    grabs fail, render logs alone fail, event loop free, wire healthy).
    A periodic no-op RHI frame keeps the pipeline primed so the first
    drag frame displays immediately. Default 250 ms (proven value);
    opt out with ``IMGSLI_DND_KEEPWARM_MS=0``. Ticks stand down while
    the canvas is hidden/minimized or while the drag pump owns frames.
    P4 attributed invalidation: the arm records once as
    ``invalidate.keepwarm.armed`` and every tick records its outcome as
    ``invalidate.keepwarm.tick`` (fired with the pending cause, or
    skipped with the stand-down reason) under
    ``IMGSLI_IC_INVALIDATE_DEBUG`` — flag off costs one env check per
    tick and the healthy-idle skip path is byte-identical.
    """
    try:
        import os as _os

        try:
            _interval = int(_os.environ.get("IMGSLI_DND_KEEPWARM_MS", "250"))
        except Exception:
            _interval = 250
        if _interval <= 0:
            return
        if getattr(widget, "_dnd_keepwarm_started", False):
            return
        widget._dnd_keepwarm_started = True
        from PySide6.QtCore import QTimer as _QTimer

        _timer = _QTimer(widget)
        _timer.setInterval(_interval)

        def _on_tick() -> None:
            try:
                from tabs.image_compare.canvas.loupe_trace import (
                    frame_context_from_widget as _fcw,
                )
                from tabs.image_compare.canvas.loupe_trace import (
                    trace_invalidation as _trace_inv,
                )

                if not widget.isVisible():
                    _trace_inv(
                        _fcw(widget),
                        "keepwarm.tick",
                        "keep-warm tick skipped: canvas hidden",
                        verdict="skipped",
                    )
                    return
                _win = widget.window()
                if _win is not None:
                    try:
                        if _win.isMinimized():
                            _trace_inv(
                                _fcw(widget),
                                "keepwarm.tick",
                                "keep-warm tick skipped: window minimized",
                                verdict="skipped",
                            )
                            return
                    except Exception:
                        pass
                try:
                    if bool(widget.runtime_state._drag_overlay_visible):
                        _trace_inv(
                            _fcw(widget),
                            "keepwarm.tick",
                            "keep-warm tick skipped: drag pump owns frames",
                            verdict="skipped",
                        )
                        return  # drag pump owns frames while shown
                except Exception:
                    pass
                try:
                    _pending = _keepwarm_pending_reason(widget)
                    if _pending is None:
                        _trace_inv(
                            _fcw(widget),
                            "keepwarm.tick",
                            "keep-warm tick skipped: healthy idle, no pending"
                            " work",
                            verdict="skipped",
                        )
                        return  # healthy idle: no pending work, skip no-op frame
                except Exception:
                    _pending = "priming"
                _trace_inv(
                    _fcw(widget),
                    "keepwarm.tick",
                    f"keep-warm tick fired: pipeline priming pending={_pending}",
                )
                widget.update()
            except Exception:
                pass

        _timer.timeout.connect(_on_tick)
        _timer.start()
        try:
            from tabs.image_compare.canvas.loupe_trace import (
                frame_context_from_widget as _fcw2,
            )
            from tabs.image_compare.canvas.loupe_trace import (
                trace_invalidation as _trace_inv2,
            )

            _trace_inv2(
                _fcw2(widget),
                "keepwarm.armed",
                f"DnD keep-warm primer armed interval_ms={_interval}"
                " (stands down when hidden/minimized, while the drag"
                " pump owns frames, and on healthy idle)",
            )
        except Exception:
            pass
        try:
            from tabs.image_compare.debug import ic_dnd_debug as _icdd

            _icdd("dnd keep-warm started interval_ms=%s", _interval)
        except Exception:
            pass
    except Exception:
        pass
