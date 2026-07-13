from tabs.host_helpers import get_overlay_layer
from tabs.image_compare.canvas.registry import registry

def _query_overlay_orientation(store) -> bool:
    query = registry().get_feature_command_by_alias("overlay.is_horizontal")
    if query is None:
        return False
    try:
        return bool(query(store))
    except AttributeError:
        return False

def update_magnifier_orientation_button_state(presenter):
    binding = registry().get_feature_toolbar_binding("magnifier.orientation")
    if binding is not None and binding.sync_state is not None:
        binding.sync_state(presenter)
    divider_visibility = registry().get_feature_toolbar_binding("magnifier.divider.visibility")
    if divider_visibility is not None and divider_visibility.sync_state is not None:
        divider_visibility.sync_state(presenter)
    divider_thickness = registry().get_feature_toolbar_binding("magnifier.divider.thickness")
    if divider_thickness is not None and divider_thickness.sync_state is not None:
        divider_thickness.sync_state(presenter)

def on_interpolation_combo_clicked(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.transient.toggle_interpolation_flyout()

def on_orientation_right_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        _show_orientation_popup(presenter)
        return
    if current_mode != "expert":
        return
    binding = registry().get_feature_toolbar_binding("divider.orientation")
    if binding is not None and binding.on_right_clicked is not None:
        binding.on_right_clicked(presenter)

def _show_orientation_popup(presenter):
    from PySide6.QtCore import QSize
    from ui.icon_manager import AppIcon, get_app_icon

    current_orientation = _query_overlay_orientation(presenter.store)
    icon_enum = (
        AppIcon.HORIZONTAL_SPLIT
        if not current_orientation
        else AppIcon.VERTICAL_SPLIT
    )
    widget = getattr(presenter, "widget", None)
    button = getattr(widget, "btn_orientation", None)
    if button is None:
        return
    overlay_layer = get_overlay_layer(button)
    if overlay_layer is None:
        return

    overlay_layer.show_popup(
        "orientation_popup",
        button,
        pixmap=get_app_icon(icon_enum).pixmap(18, 18),
        size=QSize(32, 28),
        position="top",
        offset=6,
        timeout_ms=800,
    )
