from PySide6.QtCore import QTimer

from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled

import logging

logger = logging.getLogger("ImproveImgSLI")

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
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        self._flush_scheduled = False

        # Guard: singleShot(0) is not parented — presenter/window may be
        # deleted before the timer fires (tab switch, window close). Prevent
        # libshiboken "Internal C++ object already deleted" storm.
        # Single mechanism: tabs.image_compare.canvas.live_handles (lazy
        # import — host must not bind a concrete tab at module level, see
        # tests/contracts/test_ui_tab_sandbox.py). Fail-open: any import or
        # guard failure falls through to the per-update RuntimeError catches.
        try:
            import importlib

            live_handles = importlib.import_module(
                "tabs.image_compare.canvas.live_handles"
            )
            presenter = getattr(self, "_presenter", None)
            win = getattr(presenter, "main_window_app", None) if presenter is not None else None
            if win is not None and not live_handles.is_qt_alive(win):
                return
            if presenter is not None and not live_handles.is_qt_alive(presenter):
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
