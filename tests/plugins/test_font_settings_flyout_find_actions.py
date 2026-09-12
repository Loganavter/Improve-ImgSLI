"""Font settings flyout Find Action contributions."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from core.actions.types import ActionTarget
from ui.actions.flyout_contribute import contribute_flyout_search_actions
from ui.actions.registry import ActionRegistry
from ui.actions.search_index import PROP_MEMBER, find_tagged_member
from ui.widgets.font_settings_flyout import FontSettingsFlyout
from ui.widgets.font_settings_search import font_settings_search


def test_font_settings_flyout_tags_members(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    flyout = FontSettingsFlyout(host)
    qtbot.addWidget(flyout)

    size, _ = find_tagged_member(flyout, "label.font_size")
    assert size is flyout.size_slider
    assert flyout.draw_bg_switch.property(PROP_MEMBER) == "label.draw_text_background"
    edges, _ = find_tagged_member(flyout, "label.position_edges")
    assert edges is flyout._pos_radios["edges"]


def test_font_settings_flyout_actions_listed_while_hidden(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    flyout = FontSettingsFlyout(host)
    qtbot.addWidget(flyout)
    flyout.hide()
    assert flyout.isHidden()

    shown: list[bool] = []

    def _show() -> None:
        shown.append(True)
        flyout.show()

    reg = ActionRegistry()
    title = "image_compare.action.text_settings"
    ids = contribute_flyout_search_actions(
        flyout,
        index=font_settings_search(title, include_placement=True),
        prefix="image_compare.font_settings.",
        owner_tab="image_compare",
        topic="labels",
        breadcrumb=("toolbar", "labels"),
        show_flyout=_show,
        registry=reg,
    )
    assert any(i.endswith("label.font_size") for i in ids)
    assert any(i.endswith("label.draw_text_background") for i in ids)

    listed = reg.list_for(active_tab="image_compare", query="")
    listed_ids = {a.action_id for a in listed}
    assert "image_compare.font_settings.group.image_compare.action.text_settings" in listed_ids
    size_id = (
        "image_compare.font_settings.group.image_compare.action.text_settings"
        ".label.font_size"
    )
    assert size_id in listed_ids

    size_action = next(a for a in listed if a.action_id == size_id)
    assert isinstance(size_action.target, ActionTarget)
    assert callable(size_action.target.ensure_visible)
    assert callable(size_action.target.resolve_widget)

    size_action.target.ensure_visible()
    assert shown == [True]
    assert not flyout.isHidden()
    assert size_action.target.resolve_widget() is flyout.size_slider


def test_font_settings_flyout_run_toggles_draw_background(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    flyout = FontSettingsFlyout(host)
    qtbot.addWidget(flyout)
    flyout.hide()
    flyout.draw_bg_switch.setChecked(False)

    opened: list[bool] = []

    def _show() -> None:
        opened.append(True)
        flyout.show()

    reg = ActionRegistry()
    title = "image_compare.action.text_settings"
    contribute_flyout_search_actions(
        flyout,
        index=font_settings_search(title, include_placement=True),
        prefix="image_compare.font_settings.",
        owner_tab="image_compare",
        topic="labels",
        breadcrumb=("toolbar", "labels"),
        show_flyout=_show,
        registry=reg,
    )
    action = reg.get(
        "image_compare.font_settings.group.image_compare.action.text_settings"
        ".label.draw_text_background"
    )
    assert action is not None and action.run is not None
    action.run()
    assert opened == [True]
    assert flyout.draw_bg_switch.isChecked() is True


def test_pulse_widget_parents_overlay_to_flyout(qtbot):
    from ui.actions import widget_pulse

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    flyout = FontSettingsFlyout(host)
    flyout.resize(280, 320)
    flyout.show()
    qtbot.waitExposed(flyout)
    flyout.size_slider.show()

    try:
        widget_pulse.pulse_widget(flyout.size_slider)
        overlay = widget_pulse._ACTIVE[-1]
        assert overlay is not None
        assert overlay.parentWidget() is flyout
        assert overlay.isVisible()
        assert overlay._target_rect.height() >= widget_pulse._MIN_PULSE_HEIGHT
    finally:
        widget_pulse._dispose_overlay(widget_pulse._ACTIVE[-1] if widget_pulse._ACTIVE else None)

