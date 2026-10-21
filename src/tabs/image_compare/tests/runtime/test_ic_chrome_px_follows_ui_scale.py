"""image_compare chrome geometry follows UiScale exactly once.

Sites from the ``tests/contracts/test_no_raw_chrome_px.py`` image_compare
entries, each driven through its OWN production path and built offscreen at
factor 1.0 and 1.5:

* layout spacings (``ui/layout.py``),
* video-editor dialog geometry (``plugins/video_editor/layout_geometry.py``),
* transient overlay popup sizes (``ui/transient_magnifier_instances.py``,
  ``presenters/toolbar/orientation.py``).

Each probe is design px resolved through ``scaled_px`` at use time, so the 1.5
build must equal the design value resolved once at 1.5 — not the design value
(STALE, e.g. an import bake) and not ``design * factor**2`` (DOUBLE, a
``size=`` channel that already scales internally receiving ``scaled_px``). The
canvas image-space minimum is asserted scale-INDEPENDENT on purpose (it is not
chrome design px).

Scratch objects are held in ``_HOLD`` until the session's own top-level sweep
runs: PySide6 crashes if an unparented ``QLayout`` (and its reparented items) is
garbage-collected at an arbitrary later event-loop turn.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px

from shared_toolkit.ui.overlay_layer import OverlayLayer
from tabs.image_compare.plugins.video_editor.layout_geometry import (
    apply_top_row_geometry,
    compute_minimum_dialog_width,
    compute_settings_panel_width,
)
from tabs.image_compare.presenters.toolbar.orientation import (
    on_orientation_right_clicked,
)
from tabs.image_compare.ui.layout import ImageCompareLayoutBuilder
from tabs.image_compare.ui.transient_magnifier_instances import (
    MagnifierInstancesPopupController,
)

FACTOR = 1.5
_HOLD: list = []


@pytest.fixture(autouse=True)
def _reset_ui_scale(qapp):
    yield
    UiScale.get_instance().set_factor(1.0)


def _at(factor: float, build):
    UiScale.get_instance().set_factor(factor)
    QApplication.processEvents()
    value = build()
    QApplication.processEvents()
    return value


def _check(name: str, build, design) -> None:
    """Assert ``build`` follows the scale once: 1.0 -> design, 1.5 -> scaled."""
    low = _at(1.0, build)
    high = _at(FACTOR, build)
    assert low == design, f"{name}: at 1.0 expected {design!r} (design px), got {low!r}"
    assert high == scaled_px(design), (
        f"{name}: at {FACTOR} expected {scaled_px(design)!r} (design resolved "
        f"once), got {high!r} — STALE if {design!r}, "
        f"DOUBLE if {design * FACTOR * FACTOR!r}"
    )


def _host(layout=None) -> QWidget:
    """A held top-level widget, optionally carrying ``layout``."""
    widget = QWidget()
    if layout is not None:
        widget.setLayout(layout)
    _HOLD.append(widget)
    return widget


# ---------------------------------------------------------------------------
# layout.py — QLayout spacing literals
# ---------------------------------------------------------------------------


def _fake_layout_ui():
    from sli_ui_toolkit.widgets import Text
    from ui.widgets.slider_hint import ValueSlider

    ui = SimpleNamespace(
        btn_image1=QWidget(), btn_image2=QWidget(), btn_clear_list1=QWidget(),
        btn_swap=QWidget(), btn_clear_list2=QWidget(),
        combo_image1=QWidget(), combo_image2=QWidget(),
        edit_name1=QWidget(), edit_name2=QWidget(),
        btn_text_settings=QWidget(), btn_quick_save=QWidget(),
        magnifier_settings_panel=QWidget(),
        slider_size=ValueSlider(), slider_capture=ValueSlider(), slider_speed=ValueSlider(),
        combo_interpolation=QWidget(),
        btn_orientation=QWidget(), btn_diff_mode=QWidget(), btn_channel_mode=QWidget(),
        btn_file_names=QWidget(), btn_magnifier=QWidget(),
        btn_magnifier_instances=QWidget(), btn_freeze=QWidget(),
        btn_magnifier_orientation=QWidget(), btn_magnifier_color_settings=QWidget(),
        btn_magnifier_guides=QWidget(), btn_record=QWidget(), btn_pause=QWidget(),
        btn_video_editor=QWidget(),
        image_label=QWidget(),
        length_warning_label=QWidget(),
        image_container_layout=QVBoxLayout(),
    )
    for name in (
        "label_rating1", "label_rating2", "label_edit_name1", "label_edit_name2",
        "label_magnifier_size", "label_capture_size", "label_movement_speed",
        "label_interpolation",
    ):
        setattr(ui, name, Text("x", mode="plain"))
    _HOLD.append(ui)
    return ui


def _builder() -> ImageCompareLayoutBuilder:
    ui = _fake_layout_ui()
    builder = ImageCompareLayoutBuilder(
        ui, SimpleNamespace(_current_language=lambda: "en")
    )
    # ButtonGroup construction is unrelated to the spacing sites.
    builder._button_group = lambda buttons, label_key: QWidget()
    _HOLD.append(builder)
    return builder


def _spacing_of(layout) -> int:
    _HOLD.append(layout)
    parent = _host(layout)
    return parent.layout().spacing()


def test_layout_selection_widget_spacing():
    def build():
        widget = _builder()._selection_widget(_host())
        _HOLD.append(widget)
        return widget.layout().spacing()

    _check("layout._selection_widget", build, 3)


def test_layout_button_row_spacing():
    _check("layout._button_row", lambda: _spacing_of(_builder()._button_row()), 8)


def test_layout_combobox_row_spacing():
    _check("layout._combobox_row", lambda: _spacing_of(_builder()._combobox_row()), 8)


def test_layout_checkbox_groups_spacing():
    _check(
        "layout._checkbox_groups_layout",
        lambda: _spacing_of(_builder()._checkbox_groups_layout()),
        16,
    )


def test_layout_checkbox_actions_spacing():
    _check(
        "layout._checkbox_actions_layout",
        lambda: _spacing_of(_builder()._checkbox_actions_layout()),
        8,
    )


def test_layout_edit_row_spacing():
    _check("layout._edit_layout", lambda: _spacing_of(_builder()._edit_layout()), 8)


def test_layout_slider_row_spacing():
    from tabs.image_compare.icons import Icon

    def build():
        builder = _builder()
        ui = builder.target
        row = builder._configure_slider(
            ui.slider_size, minimum=50, maximum=1000,
            icon=Icon.MAGNIFIER_SIZE, icon_attr="icon_magnifier_size",
            label=ui.label_magnifier_size, value_row_attr="value_row_slider_size",
        )
        return _spacing_of(row)

    _check("layout._configure_slider(row)", build, 8)


def test_layout_page_spacing():
    """The page-level ``QVBoxLayout`` spacing in ``build_into``."""
    def build():
        builder = _builder()
        builder._selection_widget = lambda page: QWidget(page)
        builder._checkbox_widget = lambda page: QWidget(page)
        builder._slider_panel_layout = lambda: None
        builder._image_container_widget = lambda page: QWidget(page)
        builder._create_image_startup_placeholder = lambda: None
        builder._create_zoom_indicator = lambda: None
        builder._create_info_huds = lambda: None
        builder._footer_info_widget = lambda page: QWidget(page)
        builder._edit_layout = lambda: None
        builder._save_buttons_widget = lambda page: QWidget(page)
        page = _host()
        top = builder.build_into(page)
        _HOLD.append(top)
        return top.spacing()

    _check("layout.build_into(page)", build, 6)


# ---------------------------------------------------------------------------
# video_editor/layout_geometry.py — dialog geometry constants
# ---------------------------------------------------------------------------


def _video_dialog() -> SimpleNamespace:
    return SimpleNamespace(
        settings_static_container=SimpleNamespace(
            ensurePolished=lambda: None, adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 0),
        ),
        tabs=None,
        btn_export=None,
    )


def test_video_settings_panel_width():
    dialog = _video_dialog()
    _check("video compute_settings_panel_width",
           lambda: compute_settings_panel_width(dialog), 350)


def test_video_minimum_dialog_width():
    dialog = _video_dialog()
    _check(
        "video compute_minimum_dialog_width",
        lambda: compute_minimum_dialog_width(compute_settings_panel_width(dialog)),
        620,  # 20 (margin) + 240 (preview) + 10 (spacing) + 350 (settings)
    )


def test_video_dialog_height():
    """The real ``apply_top_row_geometry`` on a widget dialog."""
    dialog = QWidget()
    _HOLD.append(dialog)
    dialog.settings_panel = QWidget(dialog)
    dialog.settings_static_container = None
    dialog.tabs = None
    dialog.btn_export = None

    def build():
        apply_top_row_geometry(dialog)
        return dialog.minimumHeight()

    _check("video apply_top_row_geometry min height", build, 600)


# ---------------------------------------------------------------------------
# Transient overlay popups — the app ``OverlayLayer.show_popup(size=...)``
# channel is a plain ``setFixedSize`` pass-through (measured), so the CALLER
# must resolve design px once.
# ---------------------------------------------------------------------------


class _Counter(QWidget):
    countChanged = Signal(int)

    def __init__(self, count: int = 2) -> None:
        super().__init__()
        self._count = count

    def magnifier_count(self) -> int:
        return self._count

    def popup_targets(self):
        return (self,)


class _PanelVisibility:
    def hide(self, **_kwargs) -> None:
        pass


class _FakeManager:
    def __init__(self, host: QWidget) -> None:
        self.host = host
        self.panel_visibility = _PanelVisibility()


def _magnifier_popup_size():
    host = _host()
    host.resize(600, 400)
    host._magn_instances_popup_open = False
    host.overlay_layer = OverlayLayer(host)
    button = _Counter(2)
    button.setParent(host)
    widget = SimpleNamespace(btn_magnifier_instances=button)
    _HOLD.append(widget)
    controller = MagnifierInstancesPopupController(_FakeManager(host), widget)
    _HOLD.append(controller)
    controller.show()
    label = host.overlay_layer._value_popups["magnifier_instances_popup"].label
    return (label.width(), label.height())


def _orientation_popup_size():
    host = _host()
    host.resize(600, 400)
    host.overlay_layer = OverlayLayer(host)
    button = QWidget(host)
    button.resize(40, 40)
    presenter = SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(ui_mode="advanced")),
        widget=SimpleNamespace(btn_orientation=button),
    )
    _HOLD.append(presenter)
    on_orientation_right_clicked(presenter)
    label = host.overlay_layer._value_popups["orientation_popup"].label
    return (label.width(), label.height())


def test_magnifier_instances_popup_size_follows_scale():
    low = _at(1.0, _magnifier_popup_size)
    high = _at(FACTOR, _magnifier_popup_size)
    assert low == (26, 24), low
    assert high == (scaled_px(26), scaled_px(24)), (
        f"magnifier popup size at {FACTOR}: expected "
        f"{(scaled_px(26), scaled_px(24))}, got {high} — "
        f"STALE if {(26, 24)}"
    )


def test_orientation_popup_size_follows_scale():
    low = _at(1.0, _orientation_popup_size)
    high = _at(FACTOR, _orientation_popup_size)
    assert low == (32, 28), low
    assert high == (scaled_px(32), scaled_px(28)), (
        f"orientation popup size at {FACTOR}: expected "
        f"{(scaled_px(32), scaled_px(28))}, got {high}"
    )


# ---------------------------------------------------------------------------
# Kept: canvas image-space minimum is deliberately NOT design px.
# ---------------------------------------------------------------------------


def test_canvas_image_label_minimum_is_scale_independent():
    from sli_ui_toolkit.widgets import Text
    from tabs.image_compare.ui.primitives import ImageComparePrimitivesFactory

    def build():
        target = SimpleNamespace(image_label=Text("x", mode="plain"))
        _HOLD.append(target)
        ImageComparePrimitivesFactory(target, None)._configure_image_label()
        return (target.image_label.minimumWidth(), target.image_label.minimumHeight())

    assert _at(1.0, build) == (200, 150)
    assert _at(FACTOR, build) == (200, 150)
