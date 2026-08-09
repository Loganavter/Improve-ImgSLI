"""Dialog-scoped Find Action contributions for the video editor plugin."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor
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

    repo = Path(__file__).resolve().parents[5]
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
