"""Schedule gate — background deferral + 500ms throttle.

Split from ``background_parts/render_flow.py`` per
``docs/dev/CODE_PATTERNS.md`` thin owner + ``use_cases/``. The schedule
path gates on ``is_background_tab`` (``stack.currentWidget`` vs
``isVisible`` fallback per ``docs/dev/tabs/isolation.md``), marks stale
when hidden, and throttles the non-interactive fps-timer arming to at most
one ``armed`` log per 500ms (``time.monotonic``). All functions take
``presenter`` as first argument.

``render_flow.py`` keeps a thin delegator that forwards to ``schedule_update``
so existing callers via ``presenter.schedule_update`` / ``coordinators`` /
``widget._flush_stale_render`` remain stable.

P4 attributed invalidation: every branch records into the live
FrameContext via ``loupe_trace.trace_invalidation`` (flag
``IMGSLI_IC_INVALIDATE_DEBUG``; off → one env check, no record) —
``schedule.fps_timer`` (armed + already-armed dedup-acks),
``schedule.interactive`` (immediate path) and ``schedule.background``
(hidden-tab stale path). Existing ``[ic-preview]`` logs are untouched.
"""

from __future__ import annotations

from tabs.image_compare.debug import ic_preview_debug as _preview_log
from tabs.image_compare.canvas.loupe_trace import (
    frame_context_from_widget,
    trace_invalidation,
)

from .background import is_background_tab, mark_render_stale

_last_schedule_log_sig = None  # type: ignore


def _invalidation_context(presenter):
    """Best-effort live FrameContext via ``presenter.widget`` (None-safe).

    Mirrors ``loupe_trace.frame_context_from_widget``: ``None`` for fakes
    or widgets without a renderer — arm sites then stay log-only.
    """
    try:
        return frame_context_from_widget(getattr(presenter, "widget", None))
    except Exception:
        return None


def schedule_update(presenter):
    import time as _time

    global _last_schedule_log_sig
    if (
        hasattr(presenter.main_window_app, "_closing")
        and presenter.main_window_app._closing
    ):
        _preview_log("schedule_update: ignored - app closing")
        return

    if is_background_tab(presenter):
        _preview_log("schedule_update: hidden tab - render marked stale")
        trace_invalidation(
            _invalidation_context(presenter),
            "schedule.background",
            "hidden tab -> marked stale, fps timer not armed",
            verdict="skipped",
        )
        mark_render_stale(presenter)
        return

    is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode

    if is_interactive:
        presenter._pending_interactive_mode = True

    # time-based throttle for fps-timer spam: at most one "armed" log per 500ms
    now = _time.monotonic()
    last_armed = getattr(schedule_update, "_last_armed_log", 0.0)

    if is_interactive:
        if _last_schedule_log_sig != "interactive":
            _last_schedule_log_sig = "interactive"
            _preview_log("schedule_update: interactive mode - immediate update")
        trace_invalidation(
            _invalidation_context(presenter),
            "schedule.interactive",
            "interactive mode -> immediate update, fps timer stopped",
        )
        presenter._update_scheduler_timer.stop()
        import time as _perf_time

        _perf_t0 = _perf_time.perf_counter()
        result = presenter.update_comparison_if_needed()
        try:
            from tabs.image_compare.debug import ic_perf_debug

            ic_perf_debug(
                "[perf] ic.render interactive %.1f ms",
                (_perf_time.perf_counter() - _perf_t0) * 1000.0,
            )
        except Exception:
            pass
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            if now - last_armed >= 0.5 or _last_schedule_log_sig != "armed":
                _last_schedule_log_sig = "armed"
                schedule_update._last_armed_log = now  # type: ignore[attr-defined]
                _preview_log("schedule_update: non-interactive - fps timer armed")
            try:
                interval_ms = int(presenter._update_scheduler_timer.interval())
            except Exception:
                interval_ms = -1
            trace_invalidation(
                _invalidation_context(presenter),
                "schedule.fps_timer",
                f"non-interactive -> fps timer armed interval_ms={interval_ms}",
            )
            presenter._update_scheduler_timer.start()
        else:
            # throttle: timer already armed — don't spam every 16ms.
            # P4: the dedup-ack itself is attributed (skipped verdict,
            # sig-throttled log) so an armed-but-never-firing timer is
            # still answerable.
            trace_invalidation(
                _invalidation_context(presenter),
                "schedule.fps_timer",
                "fps timer already armed -> dedup, no re-arm",
                verdict="skipped",
            )
