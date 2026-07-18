"""Magnifier interpolation Find Action + panel chrome."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from core.actions.types import ActionTarget
from core.constants import AppConstants
from sli_ui_toolkit.widgets import Button, ScrollableComboBox
from tabs.image_compare.ui.transient_interpolation import InterpolationFlyoutController
from ui.actions.flyout_contribute import (
    SimpleOptionAction,
    contribute_simple_options_actions,
)
from ui.actions.registry import ActionRegistry


class _FakeHost:
    def __init__(self, parent: QWidget) -> None:
        self.parent_widget = parent
        self._interp_flyout = None
        self._interp_popup_open = False
        self.main_controller = None
        self.store = SimpleNamespace(
            settings=SimpleNamespace(current_language="en"),
            viewport=SimpleNamespace(
                render_config=SimpleNamespace(
                    interpolation_method=AppConstants.DEFAULT_INTERPOLATION_METHOD
                )
            ),
            emit_state_change=lambda: None,
        )


class _FakeManager:
    def __init__(self, host: _FakeHost) -> None:
        self.host = host


def test_interpolation_ensure_opens_magnifier_panel(qtbot):
    host_widget = QWidget()
    qtbot.addWidget(host_widget)
    host_widget.resize(500, 400)
    host_widget.show()
    qtbot.waitExposed(host_widget)

    panel = QWidget(host_widget)
    panel.hide()
    combo = ScrollableComboBox(host_widget)
    for key in AppConstants.INTERPOLATION_METHODS_MAP:
        combo.addItem(key)
    combo.hide()
    btn = Button("settings", parent=host_widget, toggle=True)
    btn.setChecked(False)
    btn.show()

    toggled: list[bool] = []

    def _toggle(visible: bool) -> None:
        toggled.append(visible)
        panel.setVisible(visible)
        combo.setVisible(visible)

    widget = SimpleNamespace(
        magnifier_settings_panel=panel,
        combo_interpolation=combo,
        btn_magnifier=btn,
        toggle_magnifier_panel_visibility=_toggle,
    )

    host = _FakeHost(host_widget)
    controller = InterpolationFlyoutController(_FakeManager(host), widget)

    controller._ensure_magnifier_panel_chrome()
    assert btn.isChecked()
    assert toggled == [True]
    assert panel.isVisible()
    assert combo.isVisible()


def test_interpolation_options_listed_and_choose_data(qtbot):
    host_widget = QWidget()
    qtbot.addWidget(host_widget)
    host_widget.resize(500, 400)
    host_widget.show()
    qtbot.waitExposed(host_widget)

    panel = QWidget(host_widget)
    panel.show()
    combo = ScrollableComboBox(host_widget)
    for key in AppConstants.INTERPOLATION_METHODS_MAP:
        combo.addItem(key)
    combo.show()
    btn = Button("settings", parent=host_widget, toggle=True)
    btn.setChecked(True)

    applied: list[int] = []

    widget = SimpleNamespace(
        magnifier_settings_panel=panel,
        combo_interpolation=combo,
        btn_magnifier=btn,
        toggle_magnifier_panel_visibility=lambda _v: None,
    )
    host = _FakeHost(host_widget)
    host.main_controller = SimpleNamespace(
        on_interpolation_changed=lambda idx: applied.append(idx)
    )
    controller = InterpolationFlyoutController(_FakeManager(host), widget)

    reg = ActionRegistry()
    ids = contribute_simple_options_actions(
        controller,
        options=(
            SimpleOptionAction(
                "lanczos", "magnifier.lanczos", "LANCZOS", search_terms=("lanczos",)
            ),
            SimpleOptionAction(
                "nearest",
                "magnifier.nearest_neighbor",
                "NEAREST",
                search_terms=("nearest",),
            ),
        ),
        prefix="image_compare.interpolation.",
        owner_tab="image_compare",
        topic="magnifier",
        breadcrumb=("toolbar", "magnifier"),
        registry=reg,
    )
    assert "image_compare.interpolation.lanczos" in ids

    listed = reg.list_for(active_tab="image_compare", query="lanczos")
    assert any(a.action_id.endswith(".lanczos") for a in listed)
    action = next(a for a in listed if a.action_id.endswith(".lanczos"))
    assert isinstance(action.target, ActionTarget)
    assert callable(action.run)
    action.run()
    assert applied == [list(AppConstants.INTERPOLATION_METHODS_MAP.keys()).index("LANCZOS")]
