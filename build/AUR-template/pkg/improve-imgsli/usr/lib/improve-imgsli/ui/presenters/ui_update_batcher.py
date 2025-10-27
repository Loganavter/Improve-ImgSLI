from PyQt6.QtCore import QTimer

class UIUpdateBatcher:
    """Управляет батчингом UI-обновлений для синхронизации с Wayland"""

    def __init__(self, presenter):
        self._presenter = presenter
        self._pending_updates = set()
        self._flush_scheduled = False

    def schedule_update(self, update_type: str):
        """Регистрирует необходимость обновления определенного типа"""
        self._pending_updates.add(update_type)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush_updates)

    def schedule_batch_update(self, update_types: list):
        """Регистрирует несколько типов обновлений одновременно"""
        self._pending_updates.update(update_types)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush_updates)

    def _flush_updates(self):
        """Применяет все накопленные обновления одним тактом"""
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        self._flush_scheduled = False

        if 'combobox' in updates:
            self._presenter._do_update_combobox_displays()

        if 'file_names' in updates:
            self._presenter._do_update_file_names_display()

        if 'resolution' in updates:
            self._presenter._do_update_resolution_labels()

        if 'ratings' in updates:
            self._presenter._do_update_rating_displays()

        if 'slider_tooltips' in updates:
            self._presenter._do_update_slider_tooltips()

        if 'window_schedule' in updates:
            self._presenter.main_window_app.schedule_update()
