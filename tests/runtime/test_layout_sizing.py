"""Tests for shared layout sizing helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    HorizontalPaneMinimum,
    apply_dialog_geometry,
    clamp,
    clamp_to_screen,
    measure_scroll_pages_stack,
    widget_width_hint,
)


def test_horizontal_pane_minimum_total_width():
    spec = HorizontalPaneMinimum(
        left_min=240,
        spacing=10,
        right_min=400,
        outer_margins=20,
    )
    assert spec.total_width() == 670


def test_clamp_bounds():
    assert clamp(500, minimum=350, maximum=650) == 500
    assert clamp(100, minimum=350, maximum=650) == 350
    assert clamp(900, minimum=350, maximum=650) == 650


def test_widget_width_hint_uses_polished_size_hint():
    widget = SimpleNamespace(
        _polished=False,
        _adjusted=False,
        ensurePolished=lambda: setattr(widget, "_polished", True),
        adjustSize=lambda: setattr(widget, "_adjusted", True),
        sizeHint=lambda: SimpleNamespace(width=lambda: 412, height=lambda: 200),
    )
    assert widget_width_hint(widget) == 412
    assert widget._polished is True
    assert widget._adjusted is True


def test_widget_width_hint_default_for_missing_widget():
    assert widget_width_hint(None, default=350) == 350


def test_measure_scroll_pages_stack_uses_group_widths():
    group = SimpleNamespace(
        ensurePolished=lambda: None,
        adjustSize=lambda: None,
        sizeHint=lambda: SimpleNamespace(width=lambda: 420, height=lambda: 120),
    )
    content_widget = SimpleNamespace(
        ensurePolished=lambda: None,
        adjustSize=lambda: None,
        sizeHint=lambda: SimpleNamespace(width=lambda: 300, height=lambda: 80),
        findChildren=lambda _cls: [group],
    )
    scroll_area = SimpleNamespace(widget=lambda: content_widget)
    page_wrapper = SimpleNamespace(findChild=lambda _cls: scroll_area)

    stack = SimpleNamespace(
        count=lambda: 1,
        widget=lambda _index: page_wrapper,
    )

    width, height = measure_scroll_pages_stack(stack, group_widget_cls=object)
    assert width == 420
    assert height == 80


def test_apply_dialog_geometry_visible_dialog_only_updates_minimum_floor():
    dialog = SimpleNamespace(
        _visible=True,
        _minimum=(0, 0),
        _size=(900, 700),
        _geometry_calls=0,
        isVisible=lambda: dialog._visible,
        width=lambda: dialog._size[0],
        height=lambda: dialog._size[1],
        setMinimumSize=lambda w, h: setattr(dialog, "_minimum", (w, h)),
        updateGeometry=lambda: setattr(dialog, "_geometry_calls", dialog._geometry_calls + 1),
        resize=lambda w, h: setattr(dialog, "_size", (w, h)),
        parent=lambda: None,
    )

    apply_dialog_geometry(
        dialog,
        900,
        700,
        policy=GeometryApplyPolicy(minimum_floor=(300, 200)),
    )

    assert dialog._minimum == (300, 200)
    assert dialog._geometry_calls == 1
    assert dialog._size == (900, 700)


def test_apply_dialog_geometry_force_resize_shrinks_visible_dialog():
    dialog = SimpleNamespace(
        _visible=True,
        _minimum=(0, 0),
        _size=(1200, 900),
        _geometry_calls=0,
        isVisible=lambda: dialog._visible,
        width=lambda: dialog._size[0],
        height=lambda: dialog._size[1],
        setMinimumSize=lambda w, h: setattr(dialog, "_minimum", (w, h)),
        updateGeometry=lambda: setattr(dialog, "_geometry_calls", dialog._geometry_calls + 1),
        resize=lambda w, h: setattr(dialog, "_size", (w, h)),
        parent=lambda: None,
    )

    apply_dialog_geometry(
        dialog,
        700,
        500,
        policy=GeometryApplyPolicy(
            minimum_floor=(300, 200),
            lock_minimum_to_computed=True,
            force_resize=True,
            center_on_parent=False,
        ),
    )

    assert dialog._minimum == (700, 500)
    assert dialog._size == (700, 500)
    dialog = SimpleNamespace(
        _visible=True,
        _minimum=(0, 0),
        _size=(400, 300),
        _geometry_calls=0,
        isVisible=lambda: dialog._visible,
        width=lambda: dialog._size[0],
        height=lambda: dialog._size[1],
        setMinimumSize=lambda w, h: setattr(dialog, "_minimum", (w, h)),
        updateGeometry=lambda: setattr(dialog, "_geometry_calls", dialog._geometry_calls + 1),
        resize=lambda w, h: setattr(dialog, "_size", (w, h)),
        parent=lambda: None,
    )

    apply_dialog_geometry(
        dialog,
        900,
        700,
        policy=GeometryApplyPolicy(
            minimum_floor=(300, 200),
            lock_minimum_to_computed=True,
        ),
    )

    assert dialog._minimum == (900, 700)
    assert dialog._size == (900, 700)
    assert dialog._geometry_calls == 1


def test_apply_dialog_geometry_hidden_dialog_resizes():
    dialog = SimpleNamespace(
        _visible=False,
        _minimum=(0, 0),
        _size=(0, 0),
        _moved=False,
        isVisible=lambda: dialog._visible,
        width=lambda: dialog._size[0],
        height=lambda: dialog._size[1],
        setMinimumSize=lambda w, h: setattr(dialog, "_minimum", (w, h)),
        updateGeometry=lambda: None,
        resize=lambda w, h: setattr(dialog, "_size", (w, h)),
        parent=lambda: None,
        geometry=lambda: SimpleNamespace(
            moveCenter=lambda _center: None,
            topLeft=lambda: "0,0",
        ),
        move=lambda _pos: setattr(dialog, "_moved", True),
    )

    apply_dialog_geometry(
        dialog,
        900,
        700,
        policy=GeometryApplyPolicy(
            width_bounds=(800, 1200),
            center_on_parent=False,
        ),
    )

    assert dialog._minimum == (300, 200)
    assert dialog._size == (900, 700)


def test_apply_dialog_geometry_minimum_only_policy():
    dialog = SimpleNamespace(
        _visible=True,
        _minimum=(0, 0),
        _geometry_calls=0,
        isVisible=lambda: dialog._visible,
        width=lambda: 800,
        height=lambda: 600,
        setMinimumSize=lambda w, h: setattr(dialog, "_minimum", (w, h)),
        updateGeometry=lambda: setattr(dialog, "_geometry_calls", dialog._geometry_calls + 1),
    )

    apply_dialog_geometry(
        dialog,
        670,
        600,
        policy=GeometryApplyPolicy(
            resize_when_hidden=False,
            minimum_floor=(0, 600),
            lock_minimum_to_computed=True,
        ),
    )

    assert dialog._minimum == (670, 600)
    assert dialog._geometry_calls == 1


@pytest.mark.parametrize(
    ("height", "expected_max"),
    [(5000, True), (400, False)],
)
def test_clamp_to_screen_caps_height(height, expected_max):
    QApplication.instance() or QApplication([])
    screen = QApplication.primaryScreen()
    if screen is None:
        pytest.skip("No primary screen")

    available_h = screen.availableGeometry().height()
    _width, final_height = clamp_to_screen(900, height, margin=100)
    if expected_max:
        assert final_height <= available_h - 100
    else:
        assert final_height == height
