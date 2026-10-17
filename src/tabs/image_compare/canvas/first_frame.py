"""First-frame settle + debug for the image_compare canvas widget.

Bodies moved verbatim out of ``canvas/widget.py`` (CODE_PATTERNS thin owner +
``use_cases`` module, Part D split). Plain functions taking the widget as
their first argument; ``CanvasWidget`` keeps same-named one-line delegators,
including the Qt-required ``showEvent``/``render`` overrides. The
``firstFrameRendered`` / ``firstVisualFrameReady`` signals stay on the widget.

The present-count gate is the reason this is one module: a completed present
counts, the settle flush restacks an opaque buffer, and *only then* may the
first-frame signals fire (see ``engine/cache/first_frame_gate.py``). Splitting
the counter from the flush/emit would let the placeholder lift onto the
untouched transparent subsurface again.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer

from engine.cache.first_frame_gate import (
    FIRST_PRESENT_SETTLE_COUNT as _FIRST_PRESENT_SETTLE_COUNT,
)
from engine.frame.present import begin_source, note_presented
from tabs.image_compare.first_frame_debug import (
    ic_first_frame_debug,
    ic_first_frame_debug_enabled,
    ic_first_frame_readiness_repr,
)

from .render_context import request_update as _request_update_impl


def show_event(widget) -> None:
    """Body of ``CanvasWidget.showEvent`` (after the ``super()`` call)."""
    ic_first_frame_debug(widget, "showEvent (canvas visible)")
    widget._start_first_frame_sampler()
    widget._ensure_dnd_keepwarm()
    # Hidden stack pages never present; the first show on Windows/D3D often
    # lands on an uninitialized swapchain buffer (see-through CSD shell).
    widget._request_update()
    if widget._rhi_presents_completed < _FIRST_PRESENT_SETTLE_COUNT:
        # P4: one-shot compositor settle — attributed, fires once per
        # show until the present gate passes (bounded, not polling).
        try:
            from tabs.image_compare.canvas.loupe_trace import (
                frame_context_from_widget as _fcw0,
            )
            from tabs.image_compare.canvas.loupe_trace import (
                trace_invalidation as _trace_inv0,
            )

            _trace_inv0(
                _fcw0(widget),
                "first_present.settle",
                "first-present settle flush deferred one event-loop turn",
            )
        except Exception:
            pass
        QTimer.singleShot(0, widget._settle_first_presents)


def start_first_frame_sampler(widget) -> None:
    """Periodically log what the canvas region actually shows on screen.

    Catches the "transparent first frame" that the present timeline can't:
    the compositor may keep showing the untouched (transparent) subsurface
    even while RHI presents are being recorded. Samples every ~50 ms for
    the first ~1.5 s after show, reporting Qt-side visibility/exposure and
    the opaque fraction of a corner grab.

    P4 timer audit: this sampler is debug-gated
    (``ic_first_frame_debug_enabled``), bounded (≤30 ticks × 50 ms
    after show) and NEVER calls ``update()`` — it only logs. No
    invalidation record: no frame can come from here by construction.
    """
    if not ic_first_frame_debug_enabled():
        return
    if getattr(widget, "_ffd_sampler_started", False):
        return
    widget._ffd_sampler_started = True
    widget._ffd_sampler_ticks = 0
    from tabs.image_compare.first_frame_debug import (
        ic_first_frame_surface_repr,
    )

    def _tick():
        widget._ffd_sampler_ticks += 1
        ic_first_frame_debug(
            widget,
            "sampler presents=%s [%s]",
            widget._rhi_presents_completed,
            ic_first_frame_surface_repr(widget),
        )
        if widget._ffd_sampler_ticks < 30:
            QTimer.singleShot(50, _tick)

    QTimer.singleShot(50, _tick)


def note_present(widget) -> None:
    """Account one completed present and schedule the settle/emit chain.

    Match Multi Compare: only a completed beginPass/endPass counts as a real
    present. Emitting on a no-op (target/rhi still None) made the startup
    cover drop onto an empty D3D swapchain buffer on Windows.

    Docs: render-pass-contract (FBO α=1), qrhi-gotchas (display lags store /
    compositor), patterns (QRhiWidget under translucent CSD). On D3D the
    *first* presented buffer is often still an alpha hole through the shell;
    wait for a settle present + compositor flush. Like Multi Compare,
    firstFrameRendered is emitted only *after* that flush (see
    ``emit_first_frame_if_ready``): on Wayland/Vulkan the present is recorded
    while the compositor still shows the untouched (transparent) subsurface,
    and only flush_qrhi_compositor()'s requestUpdate/restack makes the frame
    visible. Emitting here would hide the startup placeholder a frame too
    early — the user sees the transparent subsurface until the flush lands.
    """
    if getattr(widget, "_present_debt", None) is None:
        widget._present_debt = begin_source(None)
    verdict = note_presented(widget._present_debt)  # noqa: F841 — verdict
    # intentionally unused: gates below stay on the mirror count with
    # their original </<= operators (flush→emit ordering and the ==
    # extra-settle kick must not move).
    widget._rhi_presents_completed = int(widget._present_debt.presented)
    # DnD latency probe: first completed present after the show edge.
    # Deliberately independent of FIRST_FRAME_DEBUG (whose sampler grabs
    # and would itself pump frames, confounding the measurement). Logs
    # once per show window; silent when no drag is active.
    try:
        _t0 = getattr(widget, "_dnd_show_t0", None)
        if (
            _t0 is not None
            and getattr(widget, "_dnd_first_present_t", None) is None
            and bool(
                getattr(
                    getattr(widget, "runtime_state", None),
                    "_drag_overlay_visible",
                    False,
                )
            )
        ):
            import time as _time3

            _t_first = _time3.monotonic()
            widget._dnd_first_present_t = _t_first
            from tabs.image_compare.debug import ic_dnd_debug as _icdd3

            _icdd3(
                "canvas.first-present +%sms after show (present #%s)",
                round((_t_first - _t0) * 1000),
                widget._rhi_presents_completed,
            )
    except Exception:
        pass
    ic_first_frame_debug(
        widget,
        "render() painted present #%s [%s]",
        widget._rhi_presents_completed,
        ic_first_frame_readiness_repr(widget),
    )
    if widget._rhi_presents_completed <= _FIRST_PRESENT_SETTLE_COUNT:
        widget._settle_first_presents()


def settle_first_presents(widget) -> None:
    """Settle present + window restack so the compositor shows an opaque
    frame instead of the untouched transparent subsurface (see note_present)."""

    def _flush() -> None:
        try:
            drag_vis = bool(
                getattr(
                    getattr(widget, "runtime_state", None),
                    "_drag_overlay_visible",
                    False,
                )
            )
        except Exception:
            drag_vis = False
        if drag_vis:
            # Startup settle must not fire mid-drag: its activated flush
            # (raise_/activateWindow with default activate=True) is an
            # xdg-activation storm while the drag source owns focus —
            # Mutter answers with busy-cursor flashes — plus full repaint
            # churn on the GUI thread inside the show→visible window.
            # The DnD settle chain owns restack while the zone is shown;
            # the pre-emit gate check below still runs.
            try:
                from tabs.image_compare.debug import ic_dnd_debug as _icdd0

                _icdd0("first-present settle skipped (drag overlay visible)")
            except Exception:
                pass
        else:
            try:
                from ui.canvas_infra.rhi.rhi_present_sync import (
                    flush_qrhi_compositor,
                )

                flush_qrhi_compositor(widget, reason="ic-first-present")
                ic_first_frame_debug(widget, "compositor settle flush ran")
            except Exception:
                widget._request_update()
        widget._emit_first_frame_if_ready()

    # P4: one-shot settle flush — attributed, bounded (one deferral per
    # settle call, itself gated on the present count / show edge).
    try:
        from tabs.image_compare.canvas.loupe_trace import (
            frame_context_from_widget as _fcw1,
        )
        from tabs.image_compare.canvas.loupe_trace import (
            trace_invalidation as _trace_inv1,
        )

        _trace_inv1(
            _fcw1(widget),
            "first_present.flush",
            "settle flush deferred one event-loop turn",
        )
    except Exception:
        pass
    QTimer.singleShot(0, _flush)


def emit_first_frame_if_ready(widget, visual_present_count: int) -> None:
    """Emit firstFrameRendered only once the frame is compositor-visible.

    Mirrors multi_compare's canvas_widget: called from the settle flush
    (after flush_qrhi_compositor restacks an opaque buffer), not from the
    present itself. ``visual_present_count`` is passed by the widget delegator
    so the module-level gate alias stays patchable at the widget module surface.
    """
    if widget._rhi_presents_completed < visual_present_count:
        return
    if not widget._first_frame_rendered_emitted:
        widget._first_frame_rendered_emitted = True
        ic_first_frame_debug(
            widget,
            "EMIT firstFrameRendered (presents=%s) [%s]",
            widget._rhi_presents_completed,
            ic_first_frame_readiness_repr(widget),
        )
        widget.firstFrameRendered.emit()
        widget.firstVisualFrameReady.emit()


def request_update_proxy(widget) -> None:
    """Enqueue-side present proxy (Wave C, plan-engine-perf-debugger).

    The ``ic.present_proxy`` span opens around ``request_update()``
    (which calls ``widget.update()``) and closes when it returns, so
    compositor/present time is EXCLUDED by construction — this span
    measures enqueue cost only and must never be read as photon
    timing (see H4 in the Wave C verdict: a small proxy with a
    visible stutter points at the compositor, not the CPU path).
    """
    try:
        from contextlib import nullcontext as _nullcontext

        from tabs.image_compare.canvas.loupe_trace import (
            frame_context_from_widget as _fcw,
        )

        _fc = _fcw(widget)
        _cm = (
            _fc.span(
                "ic.present_proxy",
                detail=lambda: {"source": "widget._request_update"},
            )
            if _fc is not None
            else _nullcontext()
        )
    except Exception:
        from contextlib import nullcontext as _nullcontext

        _cm = _nullcontext()
    with _cm:
        _request_update_impl(widget)
