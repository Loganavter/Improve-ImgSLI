from PySide6.QtCore import QTimer

from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled


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
            try:
                self._presenter._do_update_combobox_displays()
            except RuntimeError:
                pass

        if "file_names" in updates:
            try:
                self._presenter._do_update_file_names_display()
            except RuntimeError:
                pass
            try:
                self._presenter.schedule_canvas_update()
            except RuntimeError:
                pass

        if "resolution" in updates:
            try:
                self._presenter._do_update_resolution_labels()
            except RuntimeError:
                pass

        if "zoom_indicator" in updates:
            try:
                self._presenter._do_sync_zoom_indicator()
            except RuntimeError:
                pass

        if "ratings" in updates:
            try:
                self._presenter._do_update_rating_displays()
            except RuntimeError:
                pass

        if "window_schedule" in updates:
            try:
                self._presenter.main_window_app.schedule_update()
            except RuntimeError:
                pass
