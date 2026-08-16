"""Session-picker window minimums vs the host main-window floor.

Moved out of ``tests/runtime/test_dialog_layout_geometry.py`` (the generic
per-dialog geometry recipes stayed there): these three tests exercise
``SessionPickerWidget``'s window-minimum contract against the host
``minimum_floor_for_main_window``.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_minimum_floor_raises_for_session_picker_page():
    from ui.layout_geometry import minimum_floor_for_main_window
    from tabs.session_picker.geometry import (
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
        SESSION_PICKER_WINDOW_MIN_WIDTH,
    )

    page = SimpleNamespace(
        window_minimum_size=lambda: (
            SESSION_PICKER_WINDOW_MIN_WIDTH,
            SESSION_PICKER_WINDOW_MIN_HEIGHT,
        )
    )
    stack = SimpleNamespace(currentWidget=lambda: page)
    window = SimpleNamespace(ui=SimpleNamespace(workspace_stack=stack))
    width, height = minimum_floor_for_main_window(window)
    assert width == SESSION_PICKER_WINDOW_MIN_WIDTH
    assert height == SESSION_PICKER_WINDOW_MIN_HEIGHT


class _PickerCtx:
    def tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        if name == "list_session_blueprints":
            return ()
        if name == "get_tab_icon":
            return None
        raise RuntimeError(name)

    def get_active_session(self):
        return None


def test_session_picker_widget_declares_window_minimum(qapp):
    from tabs.session_picker.geometry import (
        SESSION_PICKER_PAGE_MIN_HEIGHT,
        SESSION_PICKER_PAGE_MIN_WIDTH,
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
        SESSION_PICKER_WINDOW_MIN_WIDTH,
    )
    from tabs.session_picker.widget import SessionPickerWidget

    widget = SessionPickerWidget(context=_PickerCtx())
    assert widget.minimumWidth() == SESSION_PICKER_PAGE_MIN_WIDTH
    assert widget.minimumHeight() == SESSION_PICKER_PAGE_MIN_HEIGHT


def test_session_picker_window_floor_never_exceeds_saved_window(qapp):
    """The main-window floor must stay design-space at any UI scale: a scaled
    floor (560 -> 840 px at 1.5x) exceeds the user's saved window height
    (e.g. 768) and forces the window taller via setMinimumSize — the shelf
    'resizes the window' when it barely fits."""
    from sli_ui_toolkit.managers import UiScale

    from tabs.session_picker.geometry import (
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
        SESSION_PICKER_WINDOW_MIN_WIDTH,
    )
    from tabs.session_picker.widget import SessionPickerWidget

    widget = SessionPickerWidget(context=_PickerCtx())
    UiScale.get_instance().set_factor(1.5)
    try:
        width, height = widget.window_minimum_size()
        assert width == SESSION_PICKER_WINDOW_MIN_WIDTH
        assert height == SESSION_PICKER_WINDOW_MIN_HEIGHT
        # The scaled floor would be 1080x840 — taller than a 768-px window.
        assert height < 768
    finally:
        UiScale.get_instance().set_factor(1.0)
    widget.deleteLater()
    assert widget.window_minimum_size() == (
        SESSION_PICKER_WINDOW_MIN_WIDTH,
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
    )
    widget.deleteLater()