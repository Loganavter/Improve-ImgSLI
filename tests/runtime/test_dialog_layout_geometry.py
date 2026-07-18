"""Tests for per-dialog layout geometry recipes."""

from __future__ import annotations

from types import SimpleNamespace

from plugins.export.layout_geometry import compute_export_dialog_size
from plugins.help.layout_geometry import compute_help_dialog_size
from plugins.image_properties.layout_geometry import compute_image_properties_dialog_size
from ui.layout_geometry import (
    compute_main_window_minimum,
    minimum_floor_for_main_window,
)


def test_compute_settings_dialog_size_caps_scroll_content_height(monkeypatch):
    """Keyboard page content is tall; shell height must not follow full scroll."""
    from plugins.settings import layout_geometry as geo

    monkeypatch.setattr(
        geo,
        "measure_scroll_pages_stack",
        lambda *_args, **_kwargs: (600, 4000),
    )
    monkeypatch.setattr(
        geo,
        "clamp_to_screen",
        lambda w, h, margin=100: (w, h),
    )

    class _Margins:
        def left(self):
            return 10

        def right(self):
            return 10

    dialog = SimpleNamespace(
        ensurePolished=lambda: None,
        sidebar=SimpleNamespace(width=lambda: 180, count=lambda: 6),
        content_layout=SimpleNamespace(contentsMargins=lambda: _Margins()),
        pages_stack=SimpleNamespace(),
        _custom_group_widget_cls=None,
    )

    _width, height = geo.compute_settings_dialog_size(dialog)
    expected = (
        geo.SETTINGS_MAX_CONTENT_HEIGHT_PX
        + geo.SETTINGS_BOTTOM_CONTROLS_HEIGHT_PX
        + geo.SETTINGS_HEIGHT_EXTRA_PX
    )
    assert height == expected
    assert height < 800


def test_compute_export_dialog_size_stacks_form_rows():
    """Form height must sum stacked rows, not take max of one row.

    Also pre-show sizing must use isHidden (children report isVisible=False
    while the parent dialog is still hidden).
    Preview frame width hints must not inflate the dialog minimum.
    """

    def _hint(w, h):
        return SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: w, height=lambda: h),
            isVisible=lambda: False,
            isHidden=lambda: False,
        )

    dialog = SimpleNamespace(
        ensurePolished=lambda: None,
        _csd_title_bar=None,
        export_preview_frame=_hint(720, 640),
        export_preview_title=_hint(120, 20),
        export_form_frame=_hint(400, 200),
        output_section=_hint(420, 140),
        fmt_label=_hint(80, 20),
        combo_format=_hint(200, 32),
        resolution_row=_hint(280, 32),
        quality_row=SimpleNamespace(isVisible=lambda: False, isHidden=lambda: True),
        png_row=_hint(400, 36),
        bg_color_row=_hint(340, 32),
        checkbox_include_metadata=_hint(220, 28),
        comment_label=_hint(100, 20),
        edit_comment=_hint(300, 28),
        checkbox_comment_default=_hint(240, 28),
        action_bar=_hint(220, 40),
    )

    width, height = compute_export_dialog_size(dialog)
    assert width >= 640
    # Inflated preview frame hint (720) must not drive minimum width.
    assert width < 720 + 420
    # Stacked form rows (~140+20+32+32+36+32+28+20+28+28+40 + spacings) >> 480
    assert height > 480
    assert height >= 520


def test_compute_help_dialog_size_uses_nav_and_pages():
    dialog = SimpleNamespace(
        ensurePolished=lambda: None,
        nav_widget=SimpleNamespace(
            ensurePolished=lambda: None,
            adjustSize=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 180, height=lambda: 300),
            minimumWidth=lambda: 200,
            count=lambda: 4,
        ),
        _pages=[
            SimpleNamespace(
                ensurePolished=lambda: None,
                adjustSize=lambda: None,
                sizeHint=lambda: SimpleNamespace(width=lambda: 520, height=lambda: 700),
            )
        ],
    )

    width, height = compute_help_dialog_size(dialog)
    assert width >= 640
    assert height >= 400


def test_compute_image_properties_dialog_size():
    section = SimpleNamespace(
        ensurePolished=lambda: None,
        sizeHint=lambda: SimpleNamespace(width=lambda: 500, height=lambda: 180),
    )
    dialog = SimpleNamespace(
        ensurePolished=lambda: None,
        properties_scroll_content=SimpleNamespace(
            ensurePolished=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 500, height=lambda: 200),
        ),
        properties_actions=SimpleNamespace(
            ensurePolished=lambda: None,
            sizeHint=lambda: SimpleNamespace(width=lambda: 220, height=lambda: 40),
        ),
        properties_section_frames=(section,),
    )

    width, height = compute_image_properties_dialog_size(dialog)
    assert width >= 480
    assert height >= 360


def test_compute_main_window_minimum_before_ui_stable():
    dialog = SimpleNamespace(_is_ui_stable=False, ui=None)
    width, height = compute_main_window_minimum(dialog)
    assert width == 260
    assert height == 310


def test_minimum_floor_raises_for_session_picker_page():
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


def test_session_picker_widget_declares_window_minimum(qapp):
    from tabs.session_picker.geometry import (
        SESSION_PICKER_PAGE_MIN_HEIGHT,
        SESSION_PICKER_PAGE_MIN_WIDTH,
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
        SESSION_PICKER_WINDOW_MIN_WIDTH,
    )
    from tabs.session_picker.widget import SessionPickerWidget

    class _Ctx:
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

    widget = SessionPickerWidget(context=_Ctx())
    assert widget.minimumWidth() == SESSION_PICKER_PAGE_MIN_WIDTH
    assert widget.minimumHeight() == SESSION_PICKER_PAGE_MIN_HEIGHT
    assert widget.window_minimum_size() == (
        SESSION_PICKER_WINDOW_MIN_WIDTH,
        SESSION_PICKER_WINDOW_MIN_HEIGHT,
    )
    widget.deleteLater()
