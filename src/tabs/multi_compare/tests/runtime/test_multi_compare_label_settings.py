"""Multi-compare label settings are local to the tab toolbar."""

from types import SimpleNamespace

from PySide6.QtGui import QColor

from plugins.settings.events import SettingsUIModeChangedEvent
from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab
from tabs.multi_compare.ui.footer import MultiCompareFooter
from tabs.multi_compare.ui.toolbar import MultiCompareToolbar
from tabs.multi_compare.widget import MultiCompareWidget


class _FakeEventBus:
    def __init__(self):
        self.subscriptions = {}

    def subscribe(self, event_type, handler):
        self.subscriptions[event_type] = handler


class _FakeSettings:
    ui_mode = "beginner"


class _FakeStore:
    def __init__(self):
        self.settings = _FakeSettings()
        self.callbacks = []

    def on_change(self, callback):
        self.callbacks.append(callback)

    def emit(self, scope):
        for callback in list(self.callbacks):
            callback(scope)


class _FakeContext:
    def __init__(self, event_bus):
        self.event_bus = event_bus

    def call_service(self, _name):
        return None


class _FakeWorkspaceStore:
    def __init__(self):
        self.sessions = {
            "a": SimpleNamespace(
                id="a",
                session_type="multi_compare",
                state_slots={},
            ),
            "b": SimpleNamespace(
                id="b",
                session_type="multi_compare",
                state_slots={},
            ),
        }
        self.active_session_id = "a"

    def get_active_workspace_session(self):
        return self.sessions[self.active_session_id]

    def ensure_session_state_slot(
        self,
        slot_name,
        *,
        session_id=None,
        factory=None,
        default=None,
        emit_change=False,
    ):
        session = self.sessions[session_id or self.active_session_id]
        if slot_name not in session.state_slots:
            session.state_slots[slot_name] = factory() if factory else default
        return session.state_slots[slot_name]

    def set_session_state_slot(
        self,
        slot_name,
        value,
        *,
        session_id=None,
        emit_scope=None,
    ):
        session = self.sessions[session_id or self.active_session_id]
        session.state_slots[slot_name] = value
        return value


def test_text_settings_button_sits_before_add_button(qapp):
    widget = MultiCompareWidget()
    layout = widget.toolbar.layout()

    assert layout.indexOf(widget.toolbar.label_group_container) < layout.indexOf(
        widget.toolbar.btn_add
    )
    assert (
        widget.toolbar.label_group_container.layout().indexOf(
            widget.toolbar.btn_text_settings
        )
        >= 0
    )


def test_toolbar_ui_modes_recompose_button_groups(qapp):
    widget = MultiCompareWidget()
    toolbar = widget.toolbar

    toolbar.apply_ui_mode("expert")

    line_layout = toolbar.line_group_container.layout()
    assert line_layout.indexOf(toolbar.btn_divider_visible) < 0
    assert line_layout.indexOf(toolbar.btn_divider_color) < 0
    assert line_layout.indexOf(toolbar.btn_divider_width) >= 0
    assert toolbar.btn_divider_visible.isHidden()
    assert toolbar.btn_divider_color.isHidden()
    assert not toolbar.btn_divider_width.isHidden()

    toolbar.apply_ui_mode("beginner")

    line_layout = toolbar.line_group_container.layout()
    assert line_layout.indexOf(toolbar.btn_divider_visible) >= 0
    assert line_layout.indexOf(toolbar.btn_divider_color) >= 0
    assert line_layout.indexOf(toolbar.btn_divider_width) >= 0
    assert not toolbar.btn_divider_visible.isHidden()
    assert not toolbar.btn_divider_color.isHidden()
    assert not toolbar.btn_divider_width.isHidden()


def test_toolbar_ui_modes_keep_tooltips_on_visible_controls(qapp):
    toolbar = MultiCompareToolbar()
    try:
        for mode in ("beginner", "advanced", "expert", "minimal"):
            toolbar.apply_ui_mode(mode)
            visible_controls = [
                toolbar.btn_divider_visible,
                toolbar.btn_divider_color,
                toolbar.btn_divider_width,
                toolbar.btn_text_settings,
                toolbar.btn_quick_save,
                toolbar.btn_settings,
                toolbar.help_button,
            ]
            missing = [
                control
                for control in visible_controls
                if control.isVisible() and not control.toolTip()
            ]

            assert missing == []

        assert toolbar.btn_add.toolTip()
        assert "tooltip." not in toolbar.btn_add.toolTip()
    finally:
        toolbar.deleteLater()


def test_footer_save_button_has_grid_export_tooltip(qapp):
    footer = MultiCompareFooter()
    try:
        assert footer.btn_save.toolTip()
        assert "grid" in footer.btn_save.toolTip().lower()
    finally:
        footer.deleteLater()


def test_multi_compare_width_button_does_not_open_color_picker(qapp):
    widget = MultiCompareWidget()
    toolbar = widget.toolbar
    requests = []
    widget.divider_color_picker_requested.connect(lambda: requests.append(True))

    assert getattr(toolbar.btn_divider_color, "_show_underline", False) is True
    assert getattr(toolbar.btn_divider_width, "_show_underline", True) is False

    if hasattr(toolbar.btn_divider_width, "rightClicked"):
        toolbar.btn_divider_width.rightClicked.emit()
    toolbar.btn_divider_color.clicked.emit()

    assert requests == [True]


def test_multi_compare_color_button_uses_divider_color(qapp):
    widget = MultiCompareWidget()
    button = widget.toolbar.btn_divider_color

    assert button._underline_config_color == QColor(
        *widget.state.divider_settings.color_rgba
    )

    widget.apply_divider_color(QColor(20, 40, 60, 220))

    assert button._underline_config_color == QColor(20, 40, 60, 220)


def test_multi_compare_width_button_opens_color_picker_in_expert(qapp):
    widget = MultiCompareWidget()
    toolbar = widget.toolbar
    requests = []
    widget.divider_color_picker_requested.connect(lambda: requests.append(True))

    toolbar.apply_ui_mode("expert")

    assert getattr(toolbar.btn_divider_width, "_show_underline", False) is True
    if hasattr(toolbar.btn_divider_width, "rightClicked"):
        toolbar.btn_divider_width.rightClicked.emit()

    assert requests == [True]


def test_multi_compare_mode_apply_resyncs_divider_underlines(qapp):
    widget = MultiCompareWidget()
    controller = MultiCompareController(widget, store=_FakeStore())

    widget.apply_divider_color(QColor(20, 40, 60, 220))
    controller._apply_ui_mode("expert", source="test")

    assert widget.toolbar.btn_divider_width._underline_config_color == QColor(
        20, 40, 60, 220
    )

    controller._apply_ui_mode("advanced", source="test")

    assert widget.toolbar.btn_divider_color._underline_config_color == QColor(
        20, 40, 60, 220
    )
    assert getattr(widget.toolbar.btn_divider_width, "_show_underline", True) is False


def test_multi_compare_state_is_saved_per_workspace_session(qapp):
    widget = MultiCompareWidget()
    tab = MultiCompareTab()
    store = _FakeWorkspaceStore()
    context = SimpleNamespace(store=store)

    tab._widget = widget
    tab._store_context = store
    widget.store.subscribe(tab._on_widget_state_changed)

    tab.on_activated(context)
    widget.apply_divider_color(QColor(10, 20, 30, 40))
    assert store.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    store.active_session_id = "b"
    tab.on_activated(context)
    # New sessions inherit the globally remembered last-used divider/label
    # settings (persisted via QSettings, see tab.py's `_default_state`) rather
    # than hardcoded defaults, so session "b" starts out matching session "a".
    assert widget.state.divider_settings.color_rgba == (10, 20, 30, 40)

    widget.apply_divider_color(QColor(1, 2, 3, 4))
    assert store.sessions["b"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )

    store.active_session_id = "a"
    tab.on_activated(context)
    assert widget.state.divider_settings.color_rgba == (10, 20, 30, 40)


def test_toolbar_minimal_mode_recomposes_action_group(qapp):
    widget = MultiCompareWidget()
    toolbar = widget.toolbar

    toolbar.apply_ui_mode("minimal")

    action_layout = toolbar.action_group_container.layout()
    assert action_layout.indexOf(toolbar.btn_quick_save) < 0
    assert action_layout.indexOf(toolbar.btn_settings) < 0
    assert action_layout.indexOf(toolbar.help_button) < 0
    assert toolbar.btn_quick_save.isHidden()
    assert toolbar.btn_settings.isHidden()
    assert toolbar.help_button.isHidden()
    assert toolbar.line_group_container.isHidden()
    assert toolbar.action_group_container.isHidden()
    assert not toolbar.label_group_container.isHidden()


def test_controller_recomposes_toolbar_on_ui_mode_event(qapp):
    widget = MultiCompareWidget()
    event_bus = _FakeEventBus()
    MultiCompareController(
        widget,
        store=_FakeStore(),
        context=_FakeContext(event_bus),
    )

    assert SettingsUIModeChangedEvent in event_bus.subscriptions

    event_bus.subscriptions[SettingsUIModeChangedEvent](
        SettingsUIModeChangedEvent("expert")
    )

    line_layout = widget.toolbar.line_group_container.layout()
    assert line_layout.indexOf(widget.toolbar.btn_divider_visible) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_color) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_width) >= 0


def test_controller_recomposes_toolbar_on_settings_store_change(qapp):
    widget = MultiCompareWidget()
    store = _FakeStore()
    MultiCompareController(
        widget,
        store=store,
        context=_FakeContext(event_bus=None),
    )

    store.settings.ui_mode = "expert"
    store.emit("settings")

    line_layout = widget.toolbar.line_group_container.layout()
    assert line_layout.indexOf(widget.toolbar.btn_divider_visible) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_color) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_width) >= 0


def test_controller_recomposes_toolbar_when_mode_changes_on_viewport_scope(qapp):
    widget = MultiCompareWidget()
    store = _FakeStore()
    MultiCompareController(
        widget,
        store=store,
        context=_FakeContext(event_bus=None),
    )

    store.settings.ui_mode = "expert"
    store.emit("viewport")

    line_layout = widget.toolbar.line_group_container.layout()
    assert line_layout.indexOf(widget.toolbar.btn_divider_visible) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_color) < 0
    assert line_layout.indexOf(widget.toolbar.btn_divider_width) >= 0


def test_font_flyout_changes_multi_compare_label_state(qapp):
    widget = MultiCompareWidget()

    widget._on_font_settings_changed(
        150,
        25,
        QColor(10, 20, 30, 255),
        QColor(1, 2, 3, 180),
        False,
        "edges",
        70,
    )

    settings = widget.state.label_settings
    assert settings.font_size_percent == 150
    assert settings.font_weight == 25
    assert settings.text_rgba == (10, 20, 30, 255)
    assert settings.bg_rgba == (1, 2, 3, 180)
    assert settings.draw_background is False
    assert settings.text_alpha_percent == 70


def test_font_flyout_opens_down_and_right_from_text_button(qapp, monkeypatch):
    widget = MultiCompareWidget()
    captured = {}

    def _capture_show_aligned(anchor_widget, **kwargs):
        captured["anchor_widget"] = anchor_widget
        captured.update(kwargs)

    monkeypatch.setattr(
        widget.font_settings_flyout, "show_aligned", _capture_show_aligned
    )

    widget._toggle_font_settings_flyout()

    assert captured["anchor_widget"] is widget.toolbar.btn_text_settings
    assert captured["anchor_point"] == "bottom-right"
    assert captured["flyout_point"] == "top-left"
