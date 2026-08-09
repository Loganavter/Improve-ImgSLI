"""Dialog-scoped Find Action contributions (export dialog + generic helpers).

Video-editor-specific coverage lives in
``src/tabs/image_compare/tests/plugins/test_video_editor_dialog_find_actions.py``
since that plugin only exists for the image_compare tab.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from plugins.export.actions import (
    contribute_export_dialog_actions,
    withdraw_export_dialog_actions,
)

EXPORT_OWNER = "image_compare"
EXPORT_PREFIX = f"{EXPORT_OWNER}.export_dialog."
from plugins.export.search import ACTIONS, BACKGROUND, OUTPUT, RESOLUTION
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
