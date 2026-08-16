"""image_compare's FontSettingsController opening the shared flyout chrome."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from domain.types import Color
from tabs.image_compare.ui.transient_font_settings import FontSettingsController
from ui.widgets.font_settings_flyout import FontSettingsFlyout


def test_font_settings_controller_opens_edit_chrome_when_hidden(qtbot):
    class _Btn(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._checked = False
            self._flyout_open = False

        def isChecked(self):
            return self._checked

        def setChecked(self, checked, emit_signal=True):  # noqa: ARG002
            self._checked = bool(checked)

        def setFlyoutOpen(self, open_):
            self._flyout_open = bool(open_)

    host_widget = QWidget()
    qtbot.addWidget(host_widget)
    host_widget.resize(200, 100)
    host_widget.show()
    qtbot.waitExposed(host_widget)
    text_btn = _Btn(host_widget)
    file_btn = _Btn(host_widget)
    text_btn.hide()
    file_btn.show()
    edit_visible = {"value": False}

    def toggle_edit(checked: bool) -> None:
        edit_visible["value"] = bool(checked)
        text_btn.setVisible(bool(checked))

    dispatched: list[object] = []

    class _Store:
        def __init__(self):
            self.viewport = SimpleNamespace(
                render_config=SimpleNamespace(
                    include_file_names_in_saved=False,
                    font_size_percent=100,
                    font_weight=50,
                    file_name_color=Color(255, 255, 255, 255),
                    file_name_bg_color=Color(0, 0, 0, 255),
                    draw_text_background=False,
                    text_placement_mode="edges",
                    text_alpha_percent=100,
                )
            )
            self.settings = SimpleNamespace(current_language="en")

        def dispatch(self, action, scope=None) -> None:  # noqa: ARG002
            dispatched.append(action)
            self.viewport.render_config.include_file_names_in_saved = True

        def get_dispatcher(self):
            return self

    ui = SimpleNamespace(
        btn_text_settings=text_btn,
        btn_file_names=file_btn,
        toggle_edit_layout_visibility=toggle_edit,
        reapply_button_styles=lambda: None,
    )
    flyout = FontSettingsFlyout(host_widget)
    flyout.hide()
    shown_anchors: list[object] = []
    flyout.show_top_left_of = lambda anchor: shown_anchors.append(anchor)

    manager_host = SimpleNamespace(
        font_settings_flyout=flyout,
        store=_Store(),
        _font_popup_open=False,
        _font_anchor_widget=None,
        parent_widget=None,
        repopulate_visible_flyouts=lambda: None,
    )
    manager = SimpleNamespace(host=manager_host)
    controller = FontSettingsController(manager, ui)
    controller.show()

    assert edit_visible["value"] is True
    assert text_btn.isVisible()
    assert any(
        type(a).__name__ == "SetIncludeFileNamesInSavedAction" for a in dispatched
    )
    assert shown_anchors == [text_btn]
    assert manager_host._font_popup_open is True