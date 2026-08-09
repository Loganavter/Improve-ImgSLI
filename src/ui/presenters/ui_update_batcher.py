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

        if "combobox" in updates:
            self._presenter._do_update_combobox_displays()

        if "file_names" in updates:
            self._presenter._do_update_file_names_display()
            self._presenter.schedule_canvas_update()

        if "resolution" in updates:
            self._presenter._do_update_resolution_labels()

        if "zoom_indicator" in updates:
            self._presenter._do_sync_zoom_indicator()

        if "ratings" in updates:
            self._presenter._do_update_rating_displays()

        if "window_schedule" in updates:
            self._presenter.main_window_app.schedule_update()
