from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_by_alias,
    get_canvas_feature_toolbar_binding,
)
from shared_toolkit.ui.overlay_layer import get_overlay_layer

def _query_overlay_orientation(store) -> bool:
    query = get_canvas_feature_command_by_alias("overlay.is_horizontal")
    return bool(query(store)) if query is not None else False

def update_magnifier_orientation_button_state(presenter):
    binding = get_canvas_feature_toolbar_binding("magnifier.orientation")
    if binding is not None and binding.sync_state is not None:
        binding.sync_state(presenter)
    divider_visibility = get_canvas_feature_toolbar_binding("magnifier.divider.visibility")
    if divider_visibility is not None and divider_visibility.sync_state is not None:
        divider_visibility.sync_state(presenter)
    divider_thickness = get_canvas_feature_toolbar_binding("magnifier.divider.thickness")
    if divider_thickness is not None and divider_thickness.sync_state is not None:
        divider_thickness.sync_state(presenter)

def on_interpolation_combo_clicked(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.transient.toggle_interpolation_flyout()

def on_orientation_right_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        _show_orientation_popup(presenter)
        binding = get_canvas_feature_toolbar_binding("magnifier.orientation")
        if binding is not None and binding.on_toggled is not None:
            current_orientation = _query_overlay_orientation(presenter.store)
            binding.on_toggled(presenter, not current_orientation)
        return
    binding = get_canvas_feature_toolbar_binding("divider.orientation")
    if binding is not None and binding.on_right_clicked is not None:
        binding.on_right_clicked(presenter)

def _show_orientation_popup(presenter):
    from PyQt6.QtCore import QSize
    from ui.icon_manager import AppIcon, get_app_icon

    current_orientation = _query_overlay_orientation(presenter.store)
    icon_enum = (
        AppIcon.HORIZONTAL_SPLIT
        if not current_orientation
        else AppIcon.VERTICAL_SPLIT
    )
    overlay_layer = get_overlay_layer(presenter.ui.btn_orientation)
    if overlay_layer is None:
        return

    overlay_layer.show_popup(
        "orientation_popup",
        presenter.ui.btn_orientation,
        pixmap=get_app_icon(icon_enum).pixmap(18, 18),
        size=QSize(32, 28),
        position="top",
        offset=6,
        timeout_ms=800,
    )
