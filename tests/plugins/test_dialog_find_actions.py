"""Dialog-scoped Find Action contributions (video editor + export)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor
from plugins.export.actions import (
    contribute_export_dialog_actions,
    withdraw_export_dialog_actions,
)

EXPORT_OWNER = "image_compare"
EXPORT_PREFIX = f"{EXPORT_OWNER}.export_dialog."
from plugins.export.search import ACTIONS, BACKGROUND, OUTPUT, RESOLUTION
from tabs.image_compare.plugins.video_editor.actions import (
    PREFIX as VIDEO_PREFIX,
    contribute_video_editor_actions,
    withdraw_video_editor_actions,
)
from tabs.image_compare.plugins.video_editor.search import (
    EXPORT_FOOTER,
    EXPORT_TABS,
    PREVIEW_QUALITY,
    RESOLUTION as VIDEO_RESOLUTION,
    TOOLBAR,
)
from sli_ui_toolkit.widgets import ComboBox
from ui.actions.registry import ActionRegistry
from ui.actions.search_index import PROP_MEMBER, group


def _clickable(parent: QWidget, *, checkable: bool = False) -> QWidget:
    w = QWidget(parent)
    state = {"checked": False, "clicks": 0}

    def click():
        state["clicks"] += 1
        if checkable:
            state["checked"] = not state["checked"]

    w.click = click  # type: ignore[attr-defined]
    if checkable:
        w.isCheckable = lambda: True  # type: ignore[attr-defined]
        w.isChecked = lambda: state["checked"]  # type: ignore[attr-defined]
        w.setChecked = lambda v: state.update(checked=bool(v))  # type: ignore[attr-defined]
    w._state = state  # type: ignore[attr-defined]
    return w


def _tag_video_dialog(dialog: QWidget) -> ComboBox:
    layout = QVBoxLayout(dialog)
    play = _clickable(dialog, checkable=True)
    TOOLBAR.tag_member(play, "button.play")
    layout.addWidget(play)
    for key in (
        "button.undo_ctrlz",
        "button.redo",
        "button.trim_to_selection",
    ):
        btn = _clickable(dialog)
        TOOLBAR.tag_member(btn, key)
        layout.addWidget(btn)

    for key in (
        "video.lock_aspect_ratio",
        "magnifier.fit_mode_toggle",
        "export.select_background_color",
    ):
        btn = _clickable(dialog, checkable=key != "export.select_background_color")
        VIDEO_RESOLUTION.tag_member(btn, key)
        layout.addWidget(btn)

    combo = ComboBox(parent=dialog)
    PREVIEW_QUALITY.tag_combo(combo)
    for key, value in (
        ("video.preview_quality_full", 1.0),
        ("video.preview_quality_balanced", 0.75),
        ("video.preview_quality_performance", 0.5),
        ("video.preview_quality_draft", 0.25),
    ):
        combo.addItem(key, value)
        PREVIEW_QUALITY.note_combo_option(combo, key)
    layout.addWidget(combo)

    tabs = QWidget(dialog)
    tabs.setCurrentWidget = lambda _p: None  # type: ignore[attr-defined]
    for key in (
        "video.standard",
        "video.manual_cli",
        "label.output",
        "video.export_log",
    ):
        page = QWidget(dialog)
        EXPORT_TABS.tag_tab_page(tabs, page, key)
        layout.addWidget(page)

    for key in (
        "action.export_video",
        "button.stop",
        "button.browse",
        "misc.set_as_favorite",
        "tooltip.use_favorite",
    ):
        btn = _clickable(dialog)
        EXPORT_FOOTER.tag_member(btn, key)
        layout.addWidget(btn)
    return combo


def _tag_export_dialog(dialog: QWidget) -> None:
    layout = QVBoxLayout(dialog)
    for key in ("button.browse", "misc.set_as_favorite", "tooltip.use_favorite"):
        btn = _clickable(dialog)
        OUTPUT.tag_member(btn, key)
        layout.addWidget(btn)
    lock = _clickable(dialog, checkable=True)
    RESOLUTION.tag_member(lock, "export.lock_aspect_ratio")
    layout.addWidget(lock)
    fill = _clickable(dialog, checkable=True)
    BACKGROUND.tag_member(fill, "export.fill_background")
    layout.addWidget(fill)
    bg = _clickable(dialog)
    BACKGROUND.tag_member(bg, "export.select_background_color")
    layout.addWidget(bg)
    for key in ("common.ok", "common.cancel", "export.include_metadata"):
        btn = _clickable(dialog, checkable=key == "export.include_metadata")
        ACTIONS.tag_member(btn, key)
        layout.addWidget(btn)


def test_video_editor_actions_register_and_withdraw(qtbot):
    registry = ActionRegistry()
    dialog = QWidget()
    qtbot.addWidget(dialog)
    combo = _tag_video_dialog(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    contribute_video_editor_actions(dialog, registry=registry)
    ids = {a.action_id for a in registry.list_for(active_tab="image_compare")}
    assert f"{VIDEO_PREFIX}group.video.toolbar.button.play" in ids
    assert f"{VIDEO_PREFIX}group.video.export_actions.action.export_video" in ids
    assert f"{VIDEO_PREFIX}group.video.export_tabs.video.standard" in ids
    assert (
        f"{VIDEO_PREFIX}group.video.preview_quality.video.preview_quality_full" in ids
    )
    assert all(a.owner_tab == "image_compare" for a in registry.all_actions())

    full = registry.get(
        f"{VIDEO_PREFIX}group.video.preview_quality.video.preview_quality_full"
    )
    assert full is not None and full.run is not None
    full.run()
    assert combo.currentIndex() == 0
    qtbot.waitUntil(lambda: combo._expanded is True, timeout=2000)
    # run commits the option; reveal-only would leave currentIndex alone.
    assert full.target is not None
    assert full.target.ensure_visible is not None
    combo.hideDropdown()
    combo.setCurrentIndex(2)
    full.target.ensure_visible()
    assert combo.currentIndex() == 2
    qtbot.waitUntil(lambda: combo._expanded is True, timeout=2000)
    assert combo._dropdown_focus_index == 0

    registry.register(
        ActionDescriptor(
            action_id="image_compare.magnifier.enabled",
            label_key="image_compare.action.magnifier",
            owner_tab="image_compare",
            run=lambda: None,
        )
    )
    withdraw_video_editor_actions(registry=registry)
    remaining = {a.action_id for a in registry.all_actions()}
    assert remaining == {"image_compare.magnifier.enabled"}
    assert not any(aid.startswith(VIDEO_PREFIX) for aid in remaining)


def test_video_editor_preview_quality_from_tagged_index(qtbot):
    from resources.translations import add_i18n_root, _manager
    from ui.actions import registry as registry_mod

    repo = Path(__file__).resolve().parents[2]
    root = repo / "src/tabs/image_compare/plugins/video_editor/resources/i18n"
    assert root.is_dir(), root
    add_i18n_root(root)
    _manager._current_lang = "ru"
    _manager._translations = _manager.ensure_loaded("ru")
    registry_mod._HAYSTACK_CACHE.clear()

    registry = ActionRegistry()
    dialog = QWidget()
    qtbot.addWidget(dialog)
    _tag_video_dialog(dialog)
    contribute_video_editor_actions(dialog, registry=registry)
    hits = registry.list_for(active_tab="image_compare", query="полное")
    assert any(
        a.action_id.endswith("video.preview_quality_full") for a in hits
    )


def test_export_dialog_actions_register_and_withdraw(qtbot):
    registry = ActionRegistry()
    dialog = QWidget()
    qtbot.addWidget(dialog)
    _tag_export_dialog(dialog)

    contribute_export_dialog_actions(
        dialog, registry=registry, owner_tab=EXPORT_OWNER
    )
    ids = {a.action_id for a in registry.list_for(active_tab=EXPORT_OWNER)}
    assert f"{EXPORT_PREFIX}group.misc.export.common.ok" in ids
    assert f"{EXPORT_PREFIX}group.label.output_directory.button.browse" in ids
    assert f"{EXPORT_PREFIX}group.misc.export.export.include_metadata" in ids

    withdraw_export_dialog_actions(registry=registry, owner_tab=EXPORT_OWNER)
    assert registry.all_actions() == []


def test_search_group_tags_generic_properties(qtbot):
    root = QWidget()
    qtbot.addWidget(root)
    g = group("label.theme", "settings.theme_dark")
    child = QWidget(root)
    g.tag_member(child, "settings.theme_dark")
    assert child.property(PROP_MEMBER) == "settings.theme_dark"


def test_install_dialog_find_action_shortcut(qtbot):
    from ui.actions.palette import install_dialog_find_action_shortcut

    dialog = QDialog()
    qtbot.addWidget(dialog)
    shortcut = install_dialog_find_action_shortcut(dialog)
    assert shortcut is not None
    assert shortcut.key().toString() == "Ctrl+Shift+P"
    assert install_dialog_find_action_shortcut(dialog) is shortcut


def test_refresh_open_dialog_find_actions(qtbot):
    from ui.actions.palette import refresh_open_dialog_find_actions

    calls: list[str] = []

    dialog = QDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._contribute_find_actions = lambda: calls.append("ok")  # type: ignore[method-assign]

    assert refresh_open_dialog_find_actions() >= 1
    assert calls == ["ok"]


def test_install_dialog_help_menu(qtbot, monkeypatch):
    from shared_toolkit.ui.decorate_dialog import (
        decorate_dialog,
        install_dialog_help_menu,
    )

    opened: list[tuple[str | None, str | None]] = []
    palette_parents: list[object] = []
    monkeypatch.setattr(
        "ui.actions.palette.dialog.open_help_page",
        lambda page=None, anchor=None: opened.append((page, anchor)),
    )
    monkeypatch.setattr(
        "ui.actions.palette.show_command_palette",
        lambda **kwargs: palette_parents.append(kwargs.get("parent")),
    )

    dialog = QDialog()
    qtbot.addWidget(dialog)
    dialog.setWindowTitle("Export")
    bar = decorate_dialog(dialog, title="Export")
    if bar is None:
        return
    strip = install_dialog_help_menu(dialog, page="export")
    assert strip is not None
    assert install_dialog_help_menu(dialog, page="export") is strip
    buttons = getattr(strip, "buttons", lambda: [])()
    assert len(buttons) >= 1
    # Trigger the Help menu actions through the same handler path as a click.
    menus = getattr(strip, "_menus", None) or []
    assert menus
    on_triggered = menus[0].on_triggered
    assert on_triggered is not None
    on_triggered("help.show", None)
    on_triggered("help.find_action", None)
    assert opened == [("export", None)]
    assert palette_parents == [dialog]
