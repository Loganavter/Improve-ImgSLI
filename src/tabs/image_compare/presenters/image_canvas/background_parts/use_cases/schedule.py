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
"""

from __future__ import annotations

from tabs.image_compare.debug import ic_preview_debug as _preview_log

from .background import is_background_tab, mark_render_stale

_last_schedule_log_sig = None  # type: ignore


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
        presenter._update_scheduler_timer.stop()
        result = presenter.update_comparison_if_needed()
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            if now - last_armed >= 0.5 or _last_schedule_log_sig != "armed":
                _last_schedule_log_sig = "armed"
                schedule_update._last_armed_log = now  # type: ignore[attr-defined]
                _preview_log("schedule_update: non-interactive - fps timer armed")
            presenter._update_scheduler_timer.start()
        else:
            # throttle: timer already armed — don't spam every 16ms
            pass
