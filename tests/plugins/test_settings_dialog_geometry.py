"""Settings dialog content changes must not resize an already visible dialog.

Dogma source: docs/dev/PRESENTERS.md §MVP boundaries; runtime UI updates should
update owned widgets, not mutate the top-level shell geometry.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from plugins.settings.dialog import SettingsDialog
from plugins.settings.dialog_shell import calculate_and_apply_geometry


class _FakeSidebar:
    def width(self) -> int:
        return 200

    def count(self) -> int:
        return 3


class _FakeStack:
    def __init__(self, widget):
        self._widget = widget

    def count(self) -> int:
        return 1

    def widget(self, _index: int):
        return self._widget


class _VisibleDialog:
    _custom_group_widget_cls = QWidget

    def __init__(self, page_wrapper):
        self.sidebar = _FakeSidebar()
        self.content_layout = QVBoxLayout()
        self.pages_stack = _FakeStack(page_wrapper)
        self.resize_calls: list[tuple[int, int]] = []
        self.minimum_size_calls: list[tuple[int, int]] = []
        self.update_geometry_calls = 0

    def ensurePolished(self) -> None:
        pass

    def setMinimumSize(self, width: int, height: int) -> None:
        self.minimum_size_calls.append((width, height))

    def isVisible(self) -> bool:
        return True

    def width(self) -> int:
        return 640

    def height(self) -> int:
        return 480

    def updateGeometry(self) -> None:
        self.update_geometry_calls += 1

    def resize(self, width: int, height: int) -> None:
        self.resize_calls.append((width, height))


def test_visible_settings_dialog_geometry_refresh_does_not_resize():
    QApplication.instance() or QApplication([])
    page_wrapper = QWidget()
    scroll_area = QScrollArea(page_wrapper)
    content_widget = QWidget()
    content_widget.setMinimumSize(420, 360)
    scroll_area.setWidget(content_widget)

    dialog = _VisibleDialog(page_wrapper)

    calculate_and_apply_geometry(dialog)

    assert dialog.resize_calls == []
    assert dialog.update_geometry_calls == 1
    assert dialog.minimum_size_calls == [(300, 200)]


def test_settings_sidebar_separates_general_from_appearance():
    QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_resolution_limit=0,
        active_tab="image_compare",
    )

    labels = [dialog.sidebar.item(i).text() for i in range(dialog.sidebar.count())]

    assert labels[:2] == ["General", "Appearance"]


def test_settings_sidebar_items_do_not_duplicate_labels_as_tooltips():
    QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_resolution_limit=0,
        active_tab="image_compare",
    )

    assert [row.button.toolTip() for row in dialog.sidebar._rows] == [""] * 5

    dialog.update_language("ru")

    assert [row.button.toolTip() for row in dialog.sidebar._rows] == [""] * 5
