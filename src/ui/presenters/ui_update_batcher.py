from PySide6.QtCore import QTimer

from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled

import logging

logger = logging.getLogger("ImproveImgSLI")

# Capability ID for the Qt-liveness probe (TabContract.create_service).
# The tab that owns the shiboken lifetime mechanism answers with a
# callable(obj) -> bool. Unknown to every tab today, so the lookup is
# fail-open None and the host-local shiboken check below preserves the
# exact verdicts the old inlined tab import used to give — until a tab
# provides the capability, no concrete tab is named anywhere here.
_LIVENESS_CAPABILITY_ID = "qt_liveness_probe"

# Cached capability resolution (_UNRESOLVED = not yet probed). This path
# is HOT (every flush), so the registry is probed once at most — never
# per-frame. The cached value may be None (no tab provides it yet).
_UNRESOLVED = object()
_cached_liveness_probe = _UNRESOLVED


def _is_qt_alive_local(obj) -> bool:
    """Host-local shiboken validity check (fail-open True).

    Same verdicts as the tab-owned probe: False only when a PySide6
    wrapper outlived its C++ object. Used when no tab provides the
    liveness capability — names no concrete tab.
    """
    try:
        import shiboken6
    except Exception:
        return True
    try:
        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def _resolve_liveness_probe():
    """Return the tab-provided liveness callable, or None (resolved once)."""
    global _cached_liveness_probe
    if _cached_liveness_probe is _UNRESOLVED:
        probe = None
        try:
            from tabs.registry import get_shared_tab_registry

            probe = get_shared_tab_registry().create_startup_service(
                _LIVENESS_CAPABILITY_ID
            )
        except Exception:
            probe = None
        if not callable(probe):
            probe = None
        _cached_liveness_probe = probe
    return _cached_liveness_probe


# A branch that keeps failing is requeued at most this many consecutive
# flushes, then dropped with an error log — unbounded requeue would reschedule
# a flush every tick forever (flush live-lock).
_MAX_BRANCH_RETRIES = 3


def _log_schedule_caller(update_types) -> None:
    if not flyout_debug_enabled():
        return
    import traceback

    caller = traceback.extract_stack()[-3]
    flyout_debug(
        "UIUpdateBatcher.schedule(%s) from %s:%d in %s",
        update_types,
        caller.filename,
        caller.lineno,
        caller.name,
    )


class UIUpdateBatcher:

    def __init__(self, presenter):
        self._presenter = presenter
        self._pending_updates = set()
        self._flush_scheduled = False
        self._branch_failures: dict[str, int] = {}

    def schedule_update(self, update_type: str):
        _log_schedule_caller(update_type)
        self._pending_updates.add(update_type)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush_updates)

    def schedule_batch_update(self, update_types: list):
        _log_schedule_caller(update_types)
        self._pending_updates.update(update_types)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush_updates)

    def _flush_updates(self):
        import os
        import time

        _perf_t0 = time.perf_counter()
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        self._flush_scheduled = False

        # Guard: singleShot(0) is not parented — presenter/window may be
        # deleted before the timer fires (tab switch, window close). Prevent
        # libshiboken "Internal C++ object already deleted" storm.
        # Routed via the ``qt_liveness_probe`` TabContract capability
        # (resolved once and cached — this path is HOT, no per-frame
        # registry scans). When no tab provides it, the host-local
        # shiboken check gives identical verdicts. Fail-open: any guard
        # failure falls through to the per-update RuntimeError catches.
        try:
            probe = _resolve_liveness_probe()
            is_alive = probe if probe is not None else _is_qt_alive_local
            presenter = getattr(self, "_presenter", None)
            win = getattr(presenter, "main_window_app", None) if presenter is not None else None
            if win is not None and not is_alive(win):
                return
            if presenter is not None and not is_alive(presenter):
                return
        except Exception:
            pass

        if "combobox" in updates:
            self._run_branch("combobox", self._do_combobox)
        if "file_names" in updates:
            self._run_branch("file_names", self._do_file_names)
        if "resolution" in updates:
            self._run_branch("resolution", self._do_resolution)
        if "zoom_indicator" in updates:
            self._run_branch("zoom_indicator", self._do_zoom_indicator)
        if "ratings" in updates:
            self._run_branch("ratings", self._do_ratings)
        if "window_schedule" in updates:
            self._run_branch("window_schedule", self._do_window_schedule)

        requeued = sorted(self._pending_updates)
        if requeued and not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush_updates)
        if os.environ.get("IMGSLI_UI_PERF_DEBUG"):
            logger.info(
                "[perf] UIUpdateBatcher flush %s %.1f ms",
                sorted(updates),
                (time.perf_counter() - _perf_t0) * 1000.0,
            )

    def _run_branch(self, update_type: str, runner) -> None:
        """Run one branch; on failure requeue it (bounded) instead of dropping.

        The pending set is already drained when branches run, so a raising
        branch must put its update type back — otherwise every update behind
        the failure is silently lost. Non-Qt errors (deleted C++ objects)
        stay silent; anything else logs.
        """
        try:
            runner()
        except RuntimeError:
            self._requeue_branch(update_type)
        except Exception:
            logger.exception("UIUpdateBatcher branch %r failed", update_type)
            self._requeue_branch(update_type)
        else:
            self._branch_failures.pop(update_type, None)

    def _requeue_branch(self, update_type: str) -> None:
        failures = self._branch_failures.get(update_type, 0) + 1
        if failures > _MAX_BRANCH_RETRIES:
            logger.error(
                "UIUpdateBatcher dropping branch %r after %d failures",
                update_type,
                failures - 1,
            )
            self._branch_failures.pop(update_type, None)
            return
        self._branch_failures[update_type] = failures
        self._pending_updates.add(update_type)

    def _do_combobox(self) -> None:
        self._presenter._do_update_combobox_displays()

    def _do_file_names(self) -> None:
        self._presenter._do_update_file_names_display()
        self._presenter.schedule_canvas_update()

    def _do_resolution(self) -> None:
        self._presenter._do_update_resolution_labels()

    def _do_zoom_indicator(self) -> None:
        self._presenter._do_sync_zoom_indicator()

    def _do_ratings(self) -> None:
        self._presenter._do_update_rating_displays()

    def _do_window_schedule(self) -> None:
        self._presenter.main_window_app.schedule_update()
