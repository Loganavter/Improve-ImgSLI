"""Find Action palette — construction and selection smoke."""

from __future__ import annotations

from PySide6.QtCore import Qt

from core.actions.types import ActionDescriptor
from ui.actions.palette.dialog import FindActionDialog
from ui.actions.registry import get_action_registry, reset_action_registry_for_tests


def test_find_action_dialog_lists_filters_and_runs(qtbot):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    ran: list[str] = []

    registry.register(
        ActionDescriptor(
            action_id="platform.settings",
            label_key="menu.settings",
            breadcrumb=("menu.file", "menu.settings"),
            run=lambda: ran.append("settings"),
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="platform.help",
            label_key="menu.show_help",
            breadcrumb=("menu.help",),
            shortcut="F1",
            run=lambda: ran.append("help"),
        )
    )

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    assert {a.action_id for a in dialog._actions} == {
        "platform.settings",
        "platform.help",
    }
    assert dialog._current_index == 0
    assert dialog._rows[0].is_current

    dialog._search.setText("help")
    # Typing debounces the rebuild so fast typing doesn't rebuild every row
    # on each keystroke — wait for it instead of expecting it synchronously.
    qtbot.wait(150)
    assert [a.action_id for a in dialog._actions] == ["platform.help"]
    assert dialog._current_index == 0

    qtbot.keyClick(dialog._search, Qt.Key.Key_Return)
    qtbot.wait(20)
    assert ran == ["help"]


def test_find_action_row_plate_click_reveals_not_runs(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from ui.actions import reveal

    reset_action_registry_for_tests()
    registry = get_action_registry()
    target = object()
    ran: list[str] = []
    revealed: list[object] = []

    registry.register(
        ActionDescriptor(
            action_id="probe.plate",
            label_key="menu.settings",
            owner_tab=None,
            run=lambda: ran.append("run"),
            target=ActionTarget(widget=target),
        )
    )
    monkeypatch.setattr(
        reveal,
        "reveal_action_target",
        lambda t, **kwargs: revealed.append(getattr(t, "widget", None)),
    )

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    row = dialog._rows[0]
    row.regionClicked.emit("_main")
    qtbot.wait(20)
    assert revealed == [target]
    assert ran == []


def test_find_action_row_run_icon_runs(qtbot):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    ran: list[str] = []
    registry.register(
        ActionDescriptor(
            action_id="probe.run_icon",
            label_key="menu.settings",
            owner_tab=None,
            run=lambda: ran.append("run"),
        )
    )
    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    dialog._rows[0].regionClicked.emit("run")
    qtbot.wait(20)
    assert ran == ["run"]


def test_find_action_dialog_empty_state(qtbot):
    reset_action_registry_for_tests()
    dialog = FindActionDialog(None, query="zzzz-no-match")
    qtbot.addWidget(dialog)
    assert not dialog._empty.isHidden()
    assert dialog._scroll.isHidden()
    assert dialog._actions == []
    assert dialog._rows == []


def test_find_action_dialog_arrow_keys_move_selection(qtbot):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    registry.register(
        ActionDescriptor(
            action_id="a.first",
            label_key="menu.settings",
            run=lambda: None,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="b.second",
            label_key="menu.show_help",
            run=lambda: None,
        )
    )
    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    assert dialog._current_index == 0
    qtbot.keyClick(dialog._search, Qt.Key.Key_Down)
    assert dialog._current_index == 1
    qtbot.keyClick(dialog._search, Qt.Key.Key_Up)
    assert dialog._current_index == 0


def test_find_action_typeahead_focuses_search(qtbot):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    registry.register(
        ActionDescriptor(
            action_id="platform.settings",
            label_key="menu.settings",
            run=lambda: None,
        )
    )
    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    # Drain the showEvent singleShot that clears search focus.
    qtbot.wait(20)
    dialog.setFocus()
    dialog._search.clearFocus()
    assert dialog.focusWidget() is not dialog._search

    qtbot.keyClick(dialog, Qt.Key.Key_H)
    assert dialog.focusWidget() is dialog._search
    assert dialog._search.text() == "h"


def test_find_action_shift_enter_reveals(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from ui.actions import reveal

    reset_action_registry_for_tests()
    registry = get_action_registry()
    target = object()
    revealed: list[object] = []

    registry.register(
        ActionDescriptor(
            action_id="probe.reveal_target",
            label_key="action.image_compare.magnifier",
            owner_tab=None,
            topic="magnifier",
            run=lambda: None,
            target=ActionTarget(widget=target),
        )
    )

    monkeypatch.setattr(
        reveal,
        "reveal_action_target",
        lambda t, **kwargs: revealed.append(getattr(t, "widget", None)),
    )

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    assert dialog._current_index == 0
    qtbot.keyClick(
        dialog._search,
        Qt.Key.Key_Return,
        modifier=Qt.KeyboardModifier.ShiftModifier,
    )
    qtbot.wait(20)
    assert revealed == [target]


def test_find_action_ctrl_enter_learns_more(qtbot, monkeypatch):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    opened: list[tuple[str, str | None]] = []

    registry.register(
        ActionDescriptor(
            action_id="probe.help_page",
            label_key="action.image_compare.magnifier",
            owner_tab=None,
            topic="magnifier",
            help_page="magnifier",
            help_anchor="overview",
            run=lambda: None,
        )
    )

    monkeypatch.setattr(
        "ui.actions.palette.dialog.open_help_page",
        lambda page, anchor=None: opened.append((page, anchor)),
    )

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    assert dialog._rows[0].has_learn_more
    qtbot.keyClick(
        dialog._search,
        Qt.Key.Key_Return,
        modifier=Qt.KeyboardModifier.ControlModifier,
    )
    qtbot.wait(20)
    assert opened == [("magnifier", "overview")]


def test_find_action_row_learn_more_click(qtbot, monkeypatch):
    reset_action_registry_for_tests()
    registry = get_action_registry()
    opened: list[tuple[str, str | None]] = []

    registry.register(
        ActionDescriptor(
            action_id="probe.help_page",
            label_key="action.image_compare.magnifier",
            owner_tab=None,
            help_page="export",
            run=lambda: None,
        )
    )
    registry.register(
        ActionDescriptor(
            action_id="probe.no_help",
            label_key="menu.quit",
            owner_tab=None,
            run=lambda: None,
        )
    )

    monkeypatch.setattr(
        "ui.actions.palette.dialog.open_help_page",
        lambda page, anchor=None: opened.append((page, anchor)),
    )

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    help_row = next(r for r in dialog._rows if r.action_id == "probe.help_page")
    no_help_row = next(r for r in dialog._rows if r.action_id == "probe.no_help")
    assert help_row.has_learn_more
    assert {r.id for r in help_row.regions()} >= {"_main", "run", "learn"}
    assert not no_help_row.has_learn_more
    assert "learn" not in {r.id for r in no_help_row.regions()}

    help_row.regionClicked.emit("learn")
    qtbot.wait(20)
    assert opened == [("export", None)]


def test_find_action_auto_pulse_on_preselect(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from ui.actions import widget_pulse

    reset_action_registry_for_tests()
    registry = get_action_registry()
    target = object()
    pulsed: list[object] = []

    registry.register(
        ActionDescriptor(
            action_id="probe.auto_pulse",
            label_key="action.image_compare.magnifier",
            owner_tab=None,
            topic="magnifier",
            run=lambda: None,
            target=ActionTarget(widget=target),
        )
    )
    monkeypatch.setattr(
        widget_pulse,
        "pulse_widget",
        lambda w, **kwargs: pulsed.append(w),
    )

    dialog = FindActionDialog(
        None,
        query="",
        preselect_action_id="probe.auto_pulse",
        auto_pulse=True,
    )
    qtbot.addWidget(dialog)
    qtbot.wait(20)
    assert pulsed == [target]


def test_reveal_menu_target_opens_strip_and_pulses_row(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from sli_ui_toolkit import TitleBarMenu, TitleBarMenuStrip
    from sli_ui_toolkit.widgets import ContextMenuAction
    from ui.actions import widget_pulse
    from ui.actions.reveal import reveal_action_target

    pulsed: list[object] = []
    monkeypatch.setattr(
        widget_pulse,
        "pulse_widget",
        lambda w, **kwargs: pulsed.append(w),
    )

    strip = TitleBarMenuStrip(
        [
            TitleBarMenu(
                label="File",
                entries=[
                    ContextMenuAction("file.settings", "Settings"),
                    ContextMenuAction("file.quit", "Quit"),
                ],
                on_triggered=lambda *_a: None,
            )
        ]
    )
    qtbot.addWidget(strip)
    strip.show()
    qtbot.waitExposed(strip)

    file_btn = strip.buttons()[0]
    reveal_action_target(
        ActionTarget(widget=file_btn, menu_action_id="file.settings"),
        delay_ms=0,
    )
    qtbot.wait(30)

    menu = strip._context_menus.get(id(file_btn))
    assert menu is not None
    assert menu.isVisible()
    row = menu.row_for_action("file.settings")
    assert row is not None
    assert pulsed == [row]


def test_platform_settings_and_help_carry_menu_targets():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    file_btn = object()
    help_btn = object()
    register_platform_actions(
        show_settings=lambda: None,
        show_help=lambda: None,
        new_session=lambda: None,
        show_find_action=lambda: None,
        quit_app=lambda: None,
        file_menu_button=file_btn,
        help_menu_button=help_btn,
        registry=registry,
    )
    settings = registry.get("platform.settings")
    help_action = registry.get("platform.help")
    assert settings is not None and settings.target is not None
    assert settings.target.widget is file_btn
    assert settings.target.menu_action_id == "file.settings"
    assert help_action is not None and help_action.target is not None
    assert help_action.target.widget is help_btn
    assert help_action.target.menu_action_id == "help.show"


def test_settings_page_actions_carry_lazy_dialog_targets():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    opened: list[str] = []
    rows: dict[str, object] = {}
    file_btn = object()

    register_platform_actions(
        show_settings=lambda: None,
        show_help=lambda: None,
        new_session=lambda: None,
        show_find_action=lambda: None,
        quit_app=lambda: None,
        show_settings_section=lambda sid: opened.append(sid),
        resolve_settings_sidebar=lambda sid: rows.setdefault(sid, object()),
        file_menu_button=file_btn,
        registry=registry,
    )
    page = registry.get("settings.page.builtin.general")
    assert page is not None and page.target is not None
    assert page.target.menu_action_id is None
    assert callable(page.target.ensure_visible)
    assert callable(page.target.resolve_widget)
    page.target.ensure_visible()
    assert opened == ["builtin.general"]
    assert page.target.resolve_widget() is rows["builtin.general"]

    platform = registry.get("platform.settings")
    assert platform is not None and platform.target is not None
    assert platform.target.widget is file_btn
    assert platform.target.menu_action_id == "file.settings"


def test_reveal_settings_page_ensure_visible_then_pulse(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from PySide6.QtWidgets import QWidget
    from ui.actions import widget_pulse
    from ui.actions.reveal import reveal_action_target

    pulsed: list[object] = []
    ensured: list[str] = []
    row = QWidget()
    qtbot.addWidget(row)
    monkeypatch.setattr(
        widget_pulse,
        "pulse_widget",
        lambda w, **kwargs: pulsed.append(w),
    )

    reveal_action_target(
        ActionTarget(
            ensure_visible=lambda: ensured.append("settings"),
            resolve_widget=lambda: row,
        ),
        delay_ms=0,
    )
    qtbot.wait(350)
    assert ensured == ["settings"]
    assert pulsed == [row]


def test_settings_sidebar_row_button_resolves(qtbot):
    """Find Action page targets must resolve to the real nav-row Button."""
    from types import SimpleNamespace

    from plugins.settings.dialog import SettingsDialog
    from sli_ui_toolkit.widgets import IconListWidget

    sidebar = IconListWidget()
    qtbot.addWidget(sidebar)
    sidebar.set_items([("General", None), ("Interface", None)])
    dialog = SimpleNamespace(
        _active_sections=(
            SimpleNamespace(section_id="builtin.general"),
            SimpleNamespace(section_id="builtin.interface"),
        ),
        sidebar=sidebar,
    )
    btn = SettingsDialog.sidebar_row_widget_for(dialog, "builtin.interface")
    assert btn is sidebar.row_button(1)
    assert btn is not None


def test_workspace_actions_carry_picker_reveal_targets():
    from core.actions.types import ActionTarget
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    registry = ActionRegistry()
    add_btn = object()
    card = object()
    opened: list[str] = []

    register_platform_actions(
        show_settings=lambda: None,
        show_help=lambda: None,
        new_session=lambda: None,
        show_find_action=lambda: None,
        quit_app=lambda: None,
        open_session_picker=lambda: opened.append("open"),
        new_image_compare=lambda: None,
        new_multi_compare=lambda: None,
        open_session_picker_target=ActionTarget(widget=add_btn),
        new_image_compare_target=ActionTarget(
            ensure_visible=lambda: opened.append("ensure"),
            resolve_widget=lambda: card,
        ),
        new_multi_compare_target=ActionTarget(
            ensure_visible=lambda: opened.append("ensure_multi"),
            resolve_widget=lambda: card,
        ),
        registry=registry,
    )
    open_picker = registry.get("workspace.open_session_picker")
    new_ic = registry.get("workspace.new_image_compare")
    assert open_picker is not None and open_picker.target is not None
    assert open_picker.target.widget is add_btn
    assert new_ic is not None and new_ic.target is not None
    assert callable(new_ic.target.ensure_visible)
    assert new_ic.target.resolve_widget() is card


def test_reveal_ensure_visible_then_pulse(qtbot, monkeypatch):
    from core.actions.types import ActionTarget
    from ui.actions import widget_pulse
    from ui.actions.reveal import reveal_action_target

    pulsed: list[object] = []
    ensured: list[str] = []
    card = object()
    monkeypatch.setattr(
        widget_pulse,
        "pulse_widget",
        lambda w, **kwargs: pulsed.append(w),
    )

    reveal_action_target(
        ActionTarget(
            ensure_visible=lambda: ensured.append("ok"),
            resolve_widget=lambda: card,
        ),
        delay_ms=0,
    )
    qtbot.wait(350)
    assert ensured == ["ok"]
    assert pulsed == [card]


def test_palette_chrome_hover_clips_to_row_capsule():
    """Chrome wash fills the region but must follow the shared row rounding."""
    import inspect

    from ui.actions.palette.row import ChromeHoverLayer

    source = inspect.getsource(ChromeHoverLayer.draw)
    assert "rounded_rect_path" in source
    assert "setClipPath" in source
    assert "drawRoundedRect" not in source
    assert "IntersectClip" in source


def test_palette_learn_region_reaches_button_right_edge(qtbot):
    """Right inset applies to Enter-only rows; Learn more spans to the edge."""
    from core.actions.types import ActionDescriptor
    from ui.actions.palette.row import ActionPaletteRow

    reset_action_registry_for_tests()
    with_help = ActionDescriptor(
        action_id="probe.learn_edge",
        label_key="menu.settings",
        run=lambda: None,
        help_page="overview",
    )
    without_help = ActionDescriptor(
        action_id="probe.run_only",
        label_key="menu.show_help",
        run=lambda: None,
    )

    row_learn = ActionPaletteRow(with_help)
    row_run = ActionPaletteRow(without_help)
    qtbot.addWidget(row_learn)
    qtbot.addWidget(row_run)
    row_learn.resize(400, 48)
    row_run.resize(400, 48)
    row_learn._controller.recompute_rects()
    row_run._controller.recompute_rects()

    learn = row_learn._controller.rects["learn"]
    assert abs(learn.right() - row_learn.width()) < 0.5

    run = row_run._controller.rects["run"]
    assert run.right() < row_run.width() - 5.0


def test_palette_plate_checked_mirrors_across_group(qtbot):
    """Title + shortcut share group=plate; CHECKED must light both regions."""
    from core.actions.types import ActionDescriptor
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
    from ui.actions.palette.row import ActionPaletteRow

    reset_action_registry_for_tests()
    action = ActionDescriptor(
        action_id="probe.plate_checked",
        label_key="menu.settings",
        shortcut="Ctrl+Shift+P",
        run=lambda: None,
    )
    row = ActionPaletteRow(action)
    qtbot.addWidget(row)
    row.resize(400, 48)
    row._controller.recompute_rects()

    assert "shortcut" in row._controller.rects
    row.setRegionChecked("_main", True)
    assert ButtonState.CHECKED in row.region_states("_main")
    assert ButtonState.CHECKED in row.region_states("shortcut")
    assert ButtonState.CHECKED not in row.region_states("run")


def test_palette_chrome_and_ripple_layers_cover_press_states():
    import inspect

    from ui.actions.palette.row import ChromeHoverLayer, PaletteRippleLayer

    chrome = inspect.getsource(ChromeHoverLayer.applies)
    assert "PRESSED" in chrome
    assert "CHECKED" in chrome

    ripple = inspect.getsource(PaletteRippleLayer.draw)
    assert "row_capsule_rect" in ripple
    assert "rounded_rect_path" in ripple