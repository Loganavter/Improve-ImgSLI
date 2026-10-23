"""Multi-compare label settings are local to the tab toolbar."""

from types import SimpleNamespace

from PySide6.QtGui import QColor

from plugins.settings.events import SettingsUIModeChangedEvent
from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.tab import MultiCompareTab
from tabs.multi_compare.use_cases.persistence import _STATE_SLOT
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

    def list_workspace_sessions(self):
        return tuple(self.sessions.values())

    def ensure_session_state_slot(
        self,
        slot_name,
        *,
        session_id=None,
        factory=None,
        default=None,
        emit_change=False,
    ):
        # Match WorkspaceStoreMixin: no emit_scope kwarg (regression for seed).
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

    def get_session_state_slot(self, slot_name, *, session_id=None, default=None):
        session = self.sessions.get(session_id or self.active_session_id)
        if session is None:
            return default
        return session.state_slots.get(slot_name, default)


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

    action_layout = toolbar.action_group_container.layout()
    assert action_layout.indexOf(toolbar.btn_quick_save) >= 0
    assert action_layout.indexOf(toolbar.btn_settings) < 0
    assert action_layout.indexOf(toolbar.help_button) < 0
    assert toolbar.btn_settings.isHidden()
    assert toolbar.help_button.isHidden()


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
    from tabs.multi_compare.tab import MultiCompareTab
    from tabs.multi_compare.tests.runtime._session_harness import FakeCoreStore

    core = FakeCoreStore(["a", "b"])
    core.ensure_slot("a")
    core.ensure_slot("b")
    widget = MultiCompareWidget(context=SimpleNamespace(store=core))
    tab = MultiCompareTab()
    tab._widget = widget
    context = SimpleNamespace(store=core)

    tab.on_activated(context)
    widget.apply_divider_color(QColor(10, 20, 30, 40))
    assert core.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    core.switch_active("b")
    tab.on_active_session_changed("b", context)
    assert widget.state.divider_settings.color_rgba == (255, 255, 255, 255)

    widget.apply_divider_color(QColor(1, 2, 3, 4))
    assert core.sessions["b"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )

    core.switch_active("a")
    tab.on_active_session_changed("a", context)
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


def _stub_last_used(monkeypatch, state=None):
    """Stub the SessionState last-used QSettings read (None = empty QSettings)."""
    from tabs.multi_compare.use_cases.persistence import chrome_extract
    from tabs.use_cases.session_state import SessionState

    values = None if state is None else chrome_extract(state)
    monkeypatch.setattr(SessionState, "_last_used_values", lambda self: values)


def test_first_multi_compare_session_seeds_from_qsettings(qapp, monkeypatch):
    from tabs.multi_compare.models import (
        MultiCompareDividerSettings,
        MultiCompareLabelSettings,
        MultiCompareState,
    )
    from tabs.multi_compare.tab import MultiCompareTab

    remembered_divider = MultiCompareDividerSettings(color_rgba=(9, 8, 7, 6))
    remembered_label = MultiCompareLabelSettings(font_size_percent=120)
    _stub_last_used(
        monkeypatch,
        MultiCompareState(divider_settings=remembered_divider, label_settings=remembered_label),
    )

    store = _FakeWorkspaceStore()
    store.sessions = {
        "mc1": SimpleNamespace(
            id="mc1",
            session_type="multi_compare",
            state_slots={},
        ),
    }
    tab = MultiCompareTab()
    tab.on_session_created("mc1", SimpleNamespace(store=store))

    state = store.sessions["mc1"].state_slots[_STATE_SLOT]
    assert state.divider_settings.color_rgba == (9, 8, 7, 6)
    assert state.label_settings.font_size_percent == 120


def test_second_multi_compare_session_seeds_last_used_colors(qapp, monkeypatch):
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareState
    from tabs.multi_compare.tab import MultiCompareTab

    _stub_last_used(
        monkeypatch,
        MultiCompareState(
            divider_settings=MultiCompareDividerSettings(color_rgba=(1, 2, 3, 4)),
        ),
    )

    store = _FakeWorkspaceStore()
    store.sessions = {
        "mc1": SimpleNamespace(id="mc1", session_type="multi_compare", state_slots={}),
    }
    tab = MultiCompareTab()
    tab.on_session_created("mc1", SimpleNamespace(store=store))

    assert store.sessions["mc1"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )

    store.sessions["mc2"] = SimpleNamespace(
        id="mc2", session_type="multi_compare", state_slots={}
    )
    tab.on_session_created("mc2", SimpleNamespace(store=store))

    assert store.sessions["mc2"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )
    # Slots stay independent after seed — mutating mc2 must not rewrite mc1.
    from dataclasses import replace

    store.set_session_state_slot(
        _STATE_SLOT,
        replace(
            store.sessions["mc2"].state_slots[_STATE_SLOT],
            divider_settings=MultiCompareDividerSettings(color_rgba=(9, 9, 9, 9)),
        ),
        session_id="mc2",
        emit_scope=None,
    )
    assert store.sessions["mc1"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )


def test_deferred_page_restores_seeded_divider_color_after_early_activation(qapp):
    """Session activate can run before deferred create_page — must still restore."""
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareState

    store = _FakeWorkspaceStore()
    store.sessions = {
        "mc1": SimpleNamespace(id="mc1", session_type="multi_compare", state_slots={}),
    }
    store.active_session_id = "mc1"
    context = SimpleNamespace(
        store=store,
        _tr=lambda key, default=None: default or key,
        main_window=None,
        call_service=lambda *_a, **_k: None,
        settings=None,
    )

    tab = MultiCompareTab()
    tab.on_session_created("mc1", context)
    store.set_session_state_slot(
        _STATE_SLOT,
        MultiCompareState(
            divider_settings=MultiCompareDividerSettings(color_rgba=(9, 8, 7, 6)),
        ),
        session_id="mc1",
        emit_scope=None,
    )

    # Activate before the page/widget exists (deferred multi_compare path).
    tab.on_active_session_changed("mc1", context)
    assert tab._widget is None
    assert tab._active_session_id == "mc1"

    page = tab.create_page(None, context)
    assert tab._widget.state.divider_settings.color_rgba == (9, 8, 7, 6)

    # Hitting activate again for the same session must keep the restored color.
    tab.on_activated(context)
    assert tab._widget.state.divider_settings.color_rgba == (9, 8, 7, 6)
    page.deleteLater()


def test_seed_after_activate_updates_live_widget(qapp, monkeypatch):
    """Workspace emit activates the tab before CreatedEvent seeds QSettings."""
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareState

    _stub_last_used(
        monkeypatch,
        MultiCompareState(
            divider_settings=MultiCompareDividerSettings(color_rgba=(9, 8, 7, 6)),
        ),
    )

    store = _FakeWorkspaceStore()
    store.sessions = {
        "mc1": SimpleNamespace(id="mc1", session_type="multi_compare", state_slots={}),
    }
    store.active_session_id = "mc1"
    context = SimpleNamespace(
        store=store,
        _tr=lambda key, default=None: default or key,
        main_window=None,
        call_service=lambda *_a, **_k: None,
        settings=None,
    )

    tab = MultiCompareTab()
    page = tab.create_page(None, context)
    # Presenter activates from workspace emit *before* CreatedEvent.
    tab.on_active_session_changed("mc1", context)
    assert tab._widget.state.divider_settings.color_rgba == (255, 255, 255, 255)

    tab.on_session_created("mc1", context)
    assert store.sessions["mc1"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        9,
        8,
        7,
        6,
    )
    assert tab._widget.state.divider_settings.color_rgba == (9, 8, 7, 6)
    page.deleteLater()


def test_replace_state_does_not_clobber_qsettings_last_prefs(qapp, monkeypatch):
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareState

    from tabs.use_cases.session_state import SessionState

    saved = []

    monkeypatch.setattr(
        SessionState,
        "remember",
        lambda self, values: saved.append(tuple(values["divider"]["color_rgba"])),
    )

    widget = MultiCompareWidget()
    tab = MultiCompareTab()
    store = _FakeWorkspaceStore()
    tab._widget = widget
    tab._store_context = store
    tab._active_session_id = "a"
    widget.store.subscribe(tab._on_widget_state_changed)

    widget.store.replace_state(
        MultiCompareState(
            divider_settings=MultiCompareDividerSettings(color_rgba=(1, 1, 1, 1)),
        )
    )
    assert saved == []

    widget.apply_divider_color(QColor(2, 3, 4, 5))
    assert saved == [(2, 3, 4, 5)]


def test_text_flyout_master_switch_hides_labels(qapp):
    """The flyout's ``Show text`` switch drives ``label_settings.visible``.

    Red-before: the flyout had style rows only, so there was no way to turn the
    per-cell filenames off at all (owner report 2026-10-23).
    """
    widget = MultiCompareWidget()
    flyout = widget.font_settings_flyout
    assert flyout.show_text_switch.isChecked() is True
    assert widget.state.label_settings.visible is True

    flyout.show_text_switch.setChecked(False)

    settings = widget.state.label_settings
    assert settings.visible is False
    # Styling is preserved: re-enabling restores the same look.
    assert settings.font_size_percent == 100
    assert settings.draw_background is True


def test_text_flyout_sync_reflects_visibility_without_dispatching(qapp):
    from dataclasses import replace

    from tabs.multi_compare.scene import actions

    widget = MultiCompareWidget()
    widget.store.dispatch(
        actions.set_label_settings(
            replace(widget.state.label_settings, visible=False)
        )
    )

    widget._sync_font_settings_flyout()

    assert widget.font_settings_flyout.show_text_switch.isChecked() is False
    assert widget.state.label_settings.visible is False


def test_style_change_keeps_labels_hidden(qapp):
    """A style edit must not silently turn the labels back on."""
    widget = MultiCompareWidget()
    widget.font_settings_flyout.show_text_switch.setChecked(False)

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
    assert settings.visible is False
    assert settings.font_size_percent == 150


def test_visibility_survives_chrome_persistence_roundtrip():
    from dataclasses import replace

    from tabs.multi_compare.models import MultiCompareState
    from tabs.multi_compare.use_cases.persistence import chrome_extract, chrome_merge

    hidden = replace(MultiCompareState().label_settings, visible=False)
    state = replace(MultiCompareState(), label_settings=hidden)

    values = chrome_extract(state)
    restored = chrome_merge(MultiCompareState(), values)

    assert restored.label_settings.visible is False
    # Omitted key (older payload) means labels on, the pre-switch behaviour.
    legacy = chrome_merge(
        MultiCompareState(), {"label": {"font_size_percent": 130}}
    )
    assert legacy.label_settings.visible is True


def test_show_text_switch_is_a_find_action(qtbot):
    """The master visibility switch is tagged, listed and runnable.

    Multi compare's flyout adds ``Show text`` (the style rows cannot hide the
    labels); it must resolve/pulse like every other row, or the control exists
    on screen but not in Find Action.
    """
    from ui.actions.flyout_contribute import contribute_flyout_search_actions
    from ui.actions.registry import ActionRegistry
    from ui.actions.search_index import find_tagged_member
    from ui.widgets.font_settings_search import font_settings_search

    widget = MultiCompareWidget()
    qtbot.addWidget(widget)
    flyout = widget.font_settings_flyout

    switch, _ = find_tagged_member(flyout, "label.show_text")
    assert switch is flyout.show_text_switch

    emitted: list[bool] = []
    flyout.labels_visibility_changed.connect(emitted.append)

    reg = ActionRegistry()
    title = "multi_compare.action.text_settings"
    contribute_flyout_search_actions(
        flyout,
        index=font_settings_search(
            title, include_placement=False, include_visibility=True
        ),
        prefix="multi_compare.font_settings.",
        owner_tab="multi_compare",
        topic="labels",
        breadcrumb=("toolbar", "labels"),
        show_flyout=flyout.show,
        registry=reg,
    )
    action = reg.get(
        "multi_compare.font_settings.group.multi_compare.action.text_settings"
        ".label.show_text"
    )
    assert action is not None and action.run is not None

    flyout.show_text_switch.setChecked(True)
    emitted.clear()
    action.run()

    assert flyout.show_text_switch.isChecked() is False
    assert emitted == [False]
