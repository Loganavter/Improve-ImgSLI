from __future__ import annotations

from domain.qt_adapters import color_to_qcolor

from .shared import set_checked_quietly, set_slider_value_quietly

def sync_magnifier_toolbar_state(presenter) -> None:
    from ..state import get_magnifier_widget_state
    from ..store import MagnifierStoreService

    ui = getattr(presenter, "ui", None)
    viewport = presenter.store.viewport
    state = get_magnifier_widget_state(viewport.view_state)
    model = MagnifierStoreService(presenter.store).get_active_or_first_magnifier()
    divider_visible = (
        bool(model.divider_visible)
        if model is not None
        else bool(state.default_divider_visible)
    )
    divider_thickness = (
        int(model.divider_thickness)
        if model is not None
        else int(state.default_divider_thickness)
    )
    divider_color = (
        model.divider_color if model is not None else state.default_divider_color
    )
    set_checked_quietly(
        getattr(ui, "btn_magnifier_divider_visible", None),
        not divider_visible,
    )
    set_slider_value_quietly(
        getattr(ui, "btn_magnifier_divider_width", None),
        divider_thickness,
    )
    if (
        hasattr(ui, "btn_magnifier_orientation")
        and hasattr(ui.btn_magnifier_orientation, "set_color")
    ):
        ui.btn_magnifier_orientation.set_color(color_to_qcolor(divider_color))

def sync_magnifier_enabled_state(presenter) -> None:
    from ..mode import MagnifierModeService
    from ..store import MagnifierStoreService, active_or_default_divider_color

    ui = getattr(presenter, "ui", None)
    scene_state = MagnifierStoreService(presenter.store)
    mode_service = MagnifierModeService(presenter.store)
    active_magnifier = scene_state.get_active_or_first_magnifier()

    set_checked_quietly(
        getattr(ui, "btn_magnifier", None),
        mode_service.resolve_button_checked(active_magnifier),
    )

    btn_instances = getattr(ui, "btn_magnifier_instances", None)
    if btn_instances is not None:
        count = len(scene_state.iter_magnifiers())
        btn_instances.set_magnifier_count(count if count > 0 else 1)
        if hasattr(btn_instances, "set_can_remove"):
            btn_instances.set_can_remove(count > 1)

    panel_visible = mode_service.should_show_panel()
    if hasattr(ui, "toggle_magnifier_panel_visibility"):
        ui.toggle_magnifier_panel_visibility(panel_visible)

    if (
        hasattr(ui, "btn_magnifier_orientation")
        and hasattr(ui.btn_magnifier_orientation, "set_color")
    ):
        viewport = presenter.store.viewport
        ui.btn_magnifier_orientation.set_color(
            color_to_qcolor(
                active_magnifier.divider_color
                if active_magnifier is not None
                else active_or_default_divider_color(viewport.view_state)
            )
        )

    for attr_name in (
        "btn_magnifier_color_settings",
        "btn_magnifier_color_settings_beginner",
    ):
        btn = getattr(ui, attr_name, None)
        if btn is not None and hasattr(btn, "refresh_visual_state"):
            btn.refresh_visual_state()

def sync_magnifier_freeze_state(presenter) -> None:
    from ..store import MagnifierStoreService

    ui = getattr(presenter, "ui", None)
    scene_state = MagnifierStoreService(presenter.store)
    set_checked_quietly(
        getattr(ui, "btn_freeze", None),
        scene_state.are_all_magnifiers_frozen(),
    )

def sync_magnifier_orientation_state(presenter) -> None:
    from ..store import (
        MagnifierStoreService,
        active_or_default_divider_color,
        active_or_default_divider_thickness,
        active_or_default_divider_visible,
    )

    ui = getattr(presenter, "ui", None)
    model = MagnifierStoreService(presenter.store).get_active_or_first_magnifier()
    magnifier_is_horizontal = bool(model.is_horizontal) if model is not None else False
    view_state = presenter.store.viewport.view_state
    magnifier_thickness = active_or_default_divider_thickness(view_state)
    magnifier_visible = active_or_default_divider_visible(view_state)
    divider_hidden = not magnifier_visible or magnifier_thickness == 0

    btn_orientation = getattr(ui, "btn_magnifier_orientation", None)
    if btn_orientation is not None:
        if divider_hidden:

            btn_orientation.blockSignals(True)
            btn_orientation._checked = True
            btn_orientation._scroll_value = 0
            btn_orientation.update()
            btn_orientation.blockSignals(False)
        else:
            set_checked_quietly(btn_orientation, magnifier_is_horizontal)
            if hasattr(btn_orientation, "set_value"):
                if btn_orientation.get_value() != magnifier_thickness:
                    btn_orientation.set_value(magnifier_thickness)
        if hasattr(btn_orientation, "set_color"):
            btn_orientation.set_color(
                color_to_qcolor(active_or_default_divider_color(view_state))
                if not divider_hidden
                else None
            )
    set_checked_quietly(
        getattr(ui, "btn_magnifier_orientation_simple", None),
        magnifier_is_horizontal,
    )

def sync_magnifier_size_state(presenter) -> None:
    from ..store import MagnifierStoreService, default_magnifier_size

    ui = getattr(presenter, "ui", None)
    scene_state = MagnifierStoreService(presenter.store)
    active_magnifier = scene_state.get_active_or_first_magnifier()
    magnifier_size = (
        float(active_magnifier.size_relative)
        if active_magnifier is not None
        else float(default_magnifier_size(presenter.store.viewport.view_state))
    )
    set_slider_value_quietly(
        getattr(ui, "slider_size", None),
        int(magnifier_size * 1000),
    )
