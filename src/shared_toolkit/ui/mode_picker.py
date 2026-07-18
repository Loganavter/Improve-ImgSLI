"""App-owned mode picker: Button click opens a SimpleOptionsFlyout."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from sli_ui_toolkit.widgets import Button, SimpleOptionsFlyout


class ModePicker(QObject):
    """Attach to a toolbar Button to pick one value from a labeled list."""

    selected = Signal(object)

    def __init__(self, button: Button, *, id_prefix: str = "mode") -> None:
        super().__init__(button)
        self._button = button
        self._actions: list[tuple[str, object]] = []
        self._current: object | None = None
        self._id_prefix = id_prefix  # kept for call-site compatibility
        self._flyout: SimpleOptionsFlyout | None = None
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

        Mouse click still opens the picker; single-key chords like ``C`` /
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

    def index_for_data(self, data: object) -> int:
        for index, (_label, value) in enumerate(self._actions):
            if value == data:
                return index
        return -1

    def open(self) -> SimpleOptionsFlyout | None:
        """Open the options list (never toggle-close).

        Find Action ``ensure_visible`` must leave the panel visible when it
        is already open — unlike a toolbar click, which toggles closed.
        """
        if not self._actions:
            return None
        flyout = self._ensure_flyout()
        if flyout is None:
            return None
        self._populate_and_show(flyout)
        return flyout

    def choose_index(self, index: int) -> None:
        """Apply the option at ``index`` (same as a row click)."""
        self._on_item_chosen(index)
        self._hide_flyout_if_open()

    def choose_data(self, data: object) -> None:
        """Apply ``data`` even when the flyout list is not open.

        Prefers a live list index when ``set_actions`` has run; otherwise
        still emits so Find Action can set a mode before the toolbar syncs.
        """
        index = self.index_for_data(data)
        if index >= 0:
            self.choose_index(index)
            return
        self._current = data
        self.selected.emit(data)
        self._hide_flyout_if_open()

    def row_widget(self, index: int):
        """Visible flyout row for pulse, or ``None`` if the list is closed."""
        flyout = self._flyout
        if flyout is None:
            return None
        getter = getattr(flyout, "row_widget", None)
        if callable(getter):
            return getter(index)
        layout = getattr(flyout, "_rows_layout", None)
        if layout is None:
            return None
        if not (0 <= index < max(0, layout.count() - 1)):
            return None
        item = layout.itemAt(index)
        return item.widget() if item is not None else None

    def _hide_flyout_if_open(self) -> None:
        flyout = self._flyout
        if flyout is not None and flyout.isVisible():
            flyout.hide()

    def _ensure_flyout(self) -> SimpleOptionsFlyout | None:
        parent = self._button.window()
        if parent is None:
            return None
        if self._flyout is None:
            self._flyout = SimpleOptionsFlyout(parent_widget=parent)
            self._flyout.item_chosen.connect(self._on_item_chosen)
        return self._flyout

    def _populate_and_show(self, flyout: SimpleOptionsFlyout) -> None:
        labels = [label for label, _data in self._actions]
        try:
            current_index = next(
                i for i, (_label, data) in enumerate(self._actions) if data == self._current
            )
        except StopIteration:
            current_index = -1
        flyout.populate(labels, current_index)
        # Left-align under the trigger (toolbar icons are narrow; show_below
        # centers and looks wrong on RGB / Diff mode buttons). Vertical slide
        # matches the magnifier interpolation dropdown drop.
        flyout.show_aligned(
            self._button,
            anchor_point="bottom-left",
            flyout_point="top-left",
            offset=2,
            animation="slide",
            animation_axis="vertical",
        )

    def _on_clicked(self) -> None:
        if not self._actions:
            return
        flyout = self._ensure_flyout()
        if flyout is None:
            return
        # Same-anchor second click closes (show_below used to do this).
        if flyout.isVisible() and getattr(flyout, "_anchor_widget", None) is self._button:
            flyout.hide()
            return
        self._populate_and_show(flyout)

    def _on_item_chosen(self, index: int) -> None:
        if not (0 <= index < len(self._actions)):
            return
        _label, data = self._actions[index]
        self._current = data
        self.selected.emit(data)
