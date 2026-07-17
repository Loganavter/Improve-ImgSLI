"""App-owned mode picker: Button click opens a checkable ContextMenu."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from sli_ui_toolkit.widgets import (
    Button,
    entries_from_labeled_data,
    popup_context_menu_for_anchor,
)


class ModePicker(QObject):
    """Attach to a toolbar Button to pick one value from a labeled list."""

    selected = Signal(object)

    def __init__(self, button: Button, *, id_prefix: str = "mode") -> None:
        super().__init__(button)
        self._button = button
        self._actions: list[tuple[str, object]] = []
        self._current: object | None = None
        self._id_prefix = id_prefix
        button.clicked.connect(self._on_clicked)

    @classmethod
    def attach(cls, button: Button, *, id_prefix: str = "mode") -> ModePicker:
        return cls(button, id_prefix=id_prefix)

    def set_actions(self, items: list[tuple[str, object]]) -> None:
        self._actions = list(items)

    def set_current(self, data: object) -> None:
        self._current = data

    def cycle_next(self) -> None:
        """Advance to the next labeled value (keyboard shortcut path).

        Mouse click still opens the picker menu; single-key chords like ``C`` /
        ``H`` should change the mode immediately without a popup.
        """
        if not self._actions:
            return
        values = [data for _label, data in self._actions]
        try:
            index = values.index(self._current)
        except ValueError:
            index = -1
        next_data = values[(index + 1) % len(values)]
        self._current = next_data
        self.selected.emit(next_data)

    def _on_clicked(self) -> None:
        if not self._actions:
            return
        parent = self._button.window()
        if parent is None:
            return
        entries = entries_from_labeled_data(
            self._actions,
            current=self._current,
            id_prefix=self._id_prefix,
        )

        def on_triggered(_action_id: str, data: object) -> None:
            self._current = data
            self.selected.emit(data)

        popup_context_menu_for_anchor(
            parent,
            self._button,
            entries,
            on_triggered=on_triggered,
        )
